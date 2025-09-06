from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Word, FrenchWord, FrenchExample, SpanishWord, SpanishExample, ItalianWord, ItalianExample, RussianWord, RussianExample, JapaneseWord, JapaneseExample
from .ai_service import process_text, process_batches, AI_PROVIDERS, get_models_for_provider
from .preprocessing import BatchProcessor
from .data_service import DataService, get_model_choices, get_field_choices
import logging
from django.urls import reverse
from django.apps import apps
from django.http import JsonResponse, Http404
from django.core.cache import cache
from django.views.decorators.http import require_POST
import json
import traceback
import datetime
import pprint
import csv
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.forms import Form, ChoiceField, MultipleChoiceField, IntegerField
from .migration_service import process_migration_item, build_input_json, find_or_create_target_word, ensure_group_link, insert_target_examples
from .migration_ai import translate_batch_with_provider
from .models import MigrationBatch, MigrationItem, LexemeGroupMember
import threading

LANG_CODE_MAP = {
    'fr': FrenchWord,
    'es': SpanishWord,
    'it': ItalianWord,
    'ru': RussianWord,
    'ja': JapaneseWord,
}

LANG_CHOICES = [
    ('fr', 'French'),
    ('es', 'Spanish'),
    ('it', 'Italian'),
    ('ru', 'Russian'),
    ('ja', 'Japanese'),
]

class MigrationForm(Form):
    source_lang = ChoiceField(choices=LANG_CHOICES)
    target_langs = MultipleChoiceField(choices=LANG_CHOICES)
    batch_size = IntegerField(min_value=1, max_value=100, initial=20)
    provider = ChoiceField(choices=[(p, p) for p in AI_PROVIDERS], initial='Gemini')
    model = ChoiceField(choices=[('auto','Auto')])

# Set up logging
logger = logging.getLogger(__name__)

# Available languages for language selection
AVAILABLE_LANGUAGES = ['French', 'Spanish', 'English', 'Russian']

# Default batch size for processing
DEFAULT_BATCH_SIZE = 20

def home(request):
    """View for the home page"""
    return render(request, 'words/home.html')

def word_list(request):
    """View to display all words"""
    words = Word.objects.all()
    return render(request, 'words/word_list.html', {'words': words})

def migrations_page(request):
    """Migrations UI page with provider/model defaults."""
    selected_provider = request.GET.get('provider', 'Gemini')
    ai_models = get_models_for_provider(selected_provider)
    if selected_provider == 'Gemini':
        preferred = 'models/gemini-2.5-flash-preview-05-20'
        if ai_models and preferred in ai_models:
            default_model = preferred
        else:
            default_model = ai_models[0] if ai_models else preferred
    else:
        default_model = ai_models[0] if ai_models else ''
    return render(request, 'words/migrations.html', {
        'default_provider': selected_provider,
        'default_model': default_model,
    })

@require_POST
def api_models_for_provider(request):
    provider = request.POST.get('provider', 'Gemini')
    models = get_models_for_provider(provider)
    return JsonResponse({'models': models})

@require_POST
def start_migration(request):
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else request.POST
        source_lang = data.get('source_lang')
        target_langs = data.get('target_langs', [])
        batch_size = int(data.get('batch_size', DEFAULT_BATCH_SIZE))
        provider = data.get('provider', 'Gemini')
        model = data.get('model') or (get_models_for_provider(provider)[0] if get_models_for_provider(provider) else '')

        last_n = int(data.get('last_n', 0)) if str(data.get('last_n', '0')).isdigit() else 0
        only_not_migrated = str(data.get('only_not_migrated', 'true')).lower() in ['true', '1', 'yes']

        # Validate
        if not source_lang or not target_langs:
            return JsonResponse({'success': False, 'message': 'Select source and at least one target language.'})
        if source_lang in target_langs:
            target_langs = [t for t in target_langs if t != source_lang]
        if not target_langs:
            return JsonResponse({'success': False, 'message': 'Targets cannot equal source.'})

        # Create batch
        from .models import MigrationBatch, MigrationItem
        batch = MigrationBatch.objects.create(
            source_language=source_lang,
            target_languages=target_langs,
            status='created'
        )

        # Build source queryset per filters
        Model = LANG_CODE_MAP[source_lang]
        qs = Model.objects.all().order_by('-id')
        # Filter out words already migrated to all requested targets (if enabled)
        if only_not_migrated:
            # Exclude any word that has a MigrationItem with status created/linked for any of target_langs
            migrated_source_ids = MigrationItem.objects.filter(
                source_language=source_lang,
                target_language__in=target_langs,
                status__in=['created','linked']
            ).values_list('source_word_id', flat=True).distinct()
            qs = qs.exclude(id__in=list(migrated_source_ids))
        if last_n > 0:
            qs = qs[:last_n]
        else:
            qs = qs[:100]
        source_ids = list(qs.values_list('id', flat=True))

        # Create items for all targets
        items = []
        for wid in source_ids:
            for tgt in target_langs:
                items.append(MigrationItem(
                    batch=batch,
                    source_language=source_lang,
                    source_word_id=wid,
                    target_language=tgt,
                    status='pending'
                ))
        MigrationItem.objects.bulk_create(items)

        # Store run params in session for UI
        request.session['migration_run'] = {
            'batch_id': batch.id,
            'source_lang': source_lang,
            'target_langs': target_langs,
            'batch_size': batch_size,
            'provider': provider,
            'model': model,
            'last_n': last_n,
            'only_not_migrated': only_not_migrated,
        }
        request.session.modified = True

        return JsonResponse({'success': True, 'batch_id': batch.id, 'items_created': len(items)})
    except Exception as e:
        logger.exception('Failed to start migration')
        return JsonResponse({'success': False, 'message': str(e)})

def french_words(request):
    """Display words page with tabs for French and Spanish"""
    # Get message from session if available
    message = request.session.pop('message', None)
    success = request.session.pop('success', True)
    
    # Get batch size from session or use default
    batch_size = request.session.get('batch_size', DEFAULT_BATCH_SIZE)
    
    # Determine active tab (fr/es/it/ru/ja)
    active_lang = request.GET.get('lang', 'fr')

    # Get all words - show most recent first by default
    if active_lang == 'es':
        words = SpanishWord.objects.all().order_by('-id')
    elif active_lang == 'it':
        words = ItalianWord.objects.all().order_by('-id')
    elif active_lang == 'ru':
        words = RussianWord.objects.all().order_by('-id')
    elif active_lang == 'ja':
        words = JapaneseWord.objects.all().order_by('-id')
    else:
        words = FrenchWord.objects.all().order_by('-id')

    # Paginate words (100 per page) so the table can be scrolled within a window
    page_number = request.GET.get('page', 1)
    paginator = Paginator(words, 100)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)
    
    # Get AI processing details from session
    preprocessing_details = request.session.get('preprocessing_details', None)
    batch_details = request.session.get('batch_details', None)
    latest_ai_response = request.session.get('latest_ai_response', None)
    ai_prompts = request.session.get('ai_prompts', None)
    processing_info = request.session.get('processing_info', None)
    
    # Get the selected provider from query parameters or use Gemini as default
    selected_provider = request.GET.get('provider', 'Gemini')
    
    # Get available AI providers and models
    ai_providers = AI_PROVIDERS
    ai_models = get_models_for_provider(selected_provider)
    
    # Set specific default model for Gemini
    if selected_provider == 'Gemini':
        # Prefer the flash preview model shown in the UI if available
        preferred = 'models/gemini-2.5-flash-preview-05-20'
        if ai_models and preferred in ai_models:
            default_model = preferred
        else:
            default_model = ai_models[0] if ai_models else preferred
    else:
        # Fallback to first available model if not Gemini or specific model not found
        default_model = ai_models[0] if ai_models else ""
    
    # Get available languages
    available_languages = AVAILABLE_LANGUAGES
    
    # Check if we have a latest response for the debug link
    has_latest_response = 'latest_ai_response' in request.session
    
    # Get model choices for deletion dropdowns
    model_choices = get_model_choices()
    
    # Get unique categories and category_2 values for filtering per language
    if active_lang == 'es':
        categories = list(SpanishWord.objects.values_list('category', flat=True).distinct())
        categories_2 = list(SpanishWord.objects.values_list('category_2', flat=True).distinct())
    elif active_lang == 'it':
        categories = list(ItalianWord.objects.values_list('category', flat=True).distinct())
        categories_2 = list(ItalianWord.objects.values_list('category_2', flat=True).distinct())
    elif active_lang == 'ru':
        categories = list(RussianWord.objects.values_list('category', flat=True).distinct())
        categories_2 = list(RussianWord.objects.values_list('category_2', flat=True).distinct())
    elif active_lang == 'ja':
        categories = list(JapaneseWord.objects.values_list('category', flat=True).distinct())
        categories_2 = list(JapaneseWord.objects.values_list('category_2', flat=True).distinct())
    else:
        categories = list(FrenchWord.objects.values_list('category', flat=True).distinct())
        categories_2 = list(FrenchWord.objects.values_list('category_2', flat=True).distinct())

    # Compute migrated targets for visible French words only
    migrated_map = {}
    if active_lang == 'fr':
        # Use only currently displayed words on the page
        source_ids = list(page_obj.object_list.values_list('id', flat=True))
        try:
            items_qs = MigrationItem.objects.filter(
                source_language='fr',
                source_word_id__in=source_ids,
                status__in=['created', 'linked']
            ).values('source_word_id', 'target_language').distinct()
            code_to_name = dict(LANG_CHOICES)
            for rec in items_qs:
                human_name = code_to_name.get(rec['target_language'], rec['target_language'])
                migrated_map.setdefault(rec['source_word_id'], set()).add(human_name)
            # Convert sets to sorted lists for template join
            migrated_map = {k: sorted(list(v)) for k, v in migrated_map.items()}
        except Exception:
            migrated_map = {}
    
    return render(request, 'words/french_words.html', {
        'french_words': page_obj.object_list,  # current page of active language
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': paginator.num_pages > 1,
        'active_lang': active_lang,
        'message': message,
        'success': success,
        'batch_size': batch_size,
        'preprocessing_details': preprocessing_details,
        'batch_details': batch_details,
        'latest_ai_response': latest_ai_response,
        'ai_prompts': ai_prompts,
        'processing_info': processing_info,
        'ai_providers': ai_providers,
        'ai_models': ai_models,
        'selected_provider': selected_provider,
        'default_model': default_model,
        'available_languages': available_languages,
        'has_latest_response': has_latest_response,
        'model_choices': model_choices,
        'categories': categories,
        'categories_2': categories_2,
        'migrated_map': migrated_map
    })

def process_french_text(request):
    """Process French text with AI and save results to database"""
    if request.method != 'POST':
        return redirect('french_words')
    
    # Get form data
    text = request.POST.get('text_content', '')
    provider = request.POST.get('provider_choice', 'OpenAI')
    model = request.POST.get('model_choice', '')
    batch_size = int(request.POST.get('batch_size', DEFAULT_BATCH_SIZE))
    
    # Save batch size in session for next use
    request.session['batch_size'] = batch_size
    
    # Get the selected language and convert to lowercase for processing
    selected_language = request.POST.get('language_choice', 'French')
    language = selected_language.lower()  # Convert to lowercase for API use
    
    if not text.strip():
        request.session['message'] = "Please enter some text to analyze"
        request.session['success'] = False
        return redirect('french_words')
    
    # Process text with AI
    try:
        # Log the request details
        logger.info(f"Processing text with provider: {provider}, model: {model}, language: {language}, batch_size: {batch_size}")
        
        # Create batch processor
        processor = BatchProcessor(text, batch_size).preprocess()
        
        # Get batch count
        batch_count = processor.get_batch_count()
        logger.info(f"Created {batch_count} batches for processing")
        
        if batch_count == 0:
            request.session['message'] = "No valid words found in the input text"
            request.session['success'] = False
            return redirect('french_words')
        
        # Print the batches for debugging
        for i in range(batch_count):
            batch = processor.get_batch(i)
            logger.info(f"Batch {i+1}/{batch_count}: {len(batch)} words")
        
        # Ensure session key exists and clear any previous stop flag
        try:
            if not request.session.session_key:
                request.session.save()
            stop_key = f"processing_stop_{request.session.session_key}"
            try:
                cache.delete(stop_key)
            except Exception:
                pass
        except Exception:
            pass

        # Store processing start time
        start_time = datetime.datetime.now()
        
        # Initialize processing info in session
        request.session['processing_info'] = {
            'total_batches': batch_count,
            'completed_batches': 0,
            'current_batch': 1,
            'start_time': str(start_time),
            'batch_times': [],
            'status': 'processing'
        }
        # Persist immediately so the polling UI can reflect initial state
        try:
            request.session.save()
        except Exception:
            pass
        
        # Process all batches - pass the request object
        success, message = process_batches(processor, provider, model, language, request)
        
        # Update processing info with completion (preserve for viewing later)
        end_time = datetime.datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        # Determine final status (respect 'stopped' set during processing)
        final_status = request.session.get('processing_info', {}).get('status', None)
        if final_status not in ['stopped']:
            final_status = 'completed' if success else 'failed'

        request.session['processing_info'].update({
            'completed_batches': request.session['processing_info'].get('completed_batches', batch_count if success else request.session['processing_info'].get('completed_batches', 0)),
            'current_batch': request.session['processing_info'].get('current_batch', batch_count),
            'end_time': str(end_time),
            'total_duration': total_duration,
            'status': final_status
        })
        # Persist final state so the UI can continue to show the last run
        try:
            request.session.save()
        except Exception:
            pass
        
        # Get all successful results
        all_results = processor.get_all_results()
        failed_details = processor.get_failed_details()
        
        # Build per-batch AI responses for UI (like prompts)
        batch_ai_responses = []
        for i in range(processor.get_batch_count()):
            per_batch = None
            for result in all_results:
                if 'batch_index' in result and result['batch_index'] == i:
                    per_batch = result
                    break
            batch_ai_responses.append({
                'batch_number': i + 1,
                'result': per_batch,
                'error': failed_details.get(i, {}).get('error') if i in processor.get_failed_batches() else None
            })
        request.session['latest_ai_response'] = {
            'provider': provider,
            'model': model,
            'input_text': text,
            'raw_response': batch_ai_responses,
            'timestamp': str(datetime.datetime.now()),
            'batch_summary': message
        }
        
        # Store preprocessing details and batch information
        preprocessing_details = processor.get_preprocessing_details()
        
        # Store batch details
        batch_details = []
        for i in range(processor.get_batch_count()):
            batch_detail = {
                'index': i,
                'batch_number': i + 1,
                'words': processor.get_batch(i),
                'prompt': processor.get_prompt(i),
                'failed': i in processor.get_failed_batches(),
                'result': None,
                'error': failed_details.get(i, {}).get('error') if i in processor.get_failed_batches() else None
            }
            
            # Add result if available
            if i not in processor.get_failed_batches():
                for result in processor.get_all_results():
                    if 'batch_index' in result and result['batch_index'] == i:
                        batch_detail['result'] = result
                        break
            
            batch_details.append(batch_detail)
        
        # Store in session (keep only preprocessing)
        request.session['preprocessing_details'] = preprocessing_details
        
        # Add a detailed AI prompt section
        ai_prompts = []
        for i in range(processor.get_batch_count()):
            prompt = processor.get_prompt(i)
            if prompt:
                ai_prompts.append({
                    'batch_number': i + 1,
                    'prompt': prompt,
                    'words': processor.get_batch(i)
                })
        
        request.session['ai_prompts'] = ai_prompts
        
        # Save results to database (only when we have successful results)
        words_added = 0
        words_skipped = 0
        
        # Choose models based on language
        if language == 'french':
            WordModel = FrenchWord
            ExampleModel = FrenchExample
            fk_name = 'french_word'
        elif language == 'spanish':
            WordModel = SpanishWord
            ExampleModel = SpanishExample
            fk_name = 'spanish_word'
        elif language == 'italian':
            WordModel = ItalianWord
            ExampleModel = ItalianExample
            fk_name = 'italian_word'
        elif language == 'russian':
            WordModel = RussianWord
            ExampleModel = RussianExample
            fk_name = 'russian_word'
        elif language == 'japanese':
            WordModel = JapaneseWord
            ExampleModel = JapaneseExample
            fk_name = 'japanese_word'
        else:
            WordModel = FrenchWord
            ExampleModel = FrenchExample
            fk_name = 'french_word'

        # Process all successful batches
        for batch_result in all_results:
            words_data = batch_result.get('words', [])
            # Some providers may include input words under a different key; ignore it
            if isinstance(words_data, list) and words_data and isinstance(words_data[0], str):
                # This is likely the input echo, skip saving
                logger.warning("AI returned a words list of strings only; skipping this payload as invalid.")
                continue
            
            for word_data in words_data:
                # Ensure we only process dict-like items
                if not isinstance(word_data, dict):
                    logger.warning(f"Skipping non-dict word_data: {word_data}")
                    continue
                # Skip if no forms provided
                if not any([
                    word_data.get('noun_form'),
                    word_data.get('verb_form'),
                    word_data.get('adjective_form'),
                    word_data.get('adverb_form')
                ]):
                    continue
                
                try:
                    # Create word record
                    create_kwargs = dict(
                        noun_form=word_data.get('noun_form'),
                        verb_form=word_data.get('verb_form'),
                        adjective_form=word_data.get('adjective_form'),
                        adverb_form=word_data.get('adverb_form'),
                        synonym_noun_form=word_data.get('synonym_noun_form'),
                        synonym_verb_form=word_data.get('synonym_verb_form'),
                        synonym_adjective_form=word_data.get('synonym_adjective_form'),
                        synonym_adverb_form=word_data.get('synonym_adverb_form'),
                        antonym_noun_form=word_data.get('antonym_noun_form'),
                        antonym_verb_form=word_data.get('antonym_verb_form'),
                        antonym_adjective_form=word_data.get('antonym_adjective_form'),
                        antonym_adverb_form=word_data.get('antonym_adverb_form'),
                        original_phrase=word_data.get('original_phrase', ''),
                        frequency=word_data.get('frequency', ''),
                        category=word_data.get('category', ''),
                        category_2=word_data.get('category_2', ''),
                        explanation=word_data.get('explanation', ''),
                    )
                    # Add Japanese-only fields only when creating Japanese entries
                    if language == 'japanese':
                        create_kwargs.update({
                            'kanji_form': word_data.get('kanji_form'),
                            'kana_reading': word_data.get('kana_reading'),
                            'romaji': word_data.get('romaji'),
                            'furigana': word_data.get('furigana'),
                        })
                    created_word = WordModel.objects.create(**create_kwargs)

                    # Create example records
                    examples = word_data.get('examples', [])
                    for example in examples:
                        if example:
                            kwargs = { fk_name: created_word, 'example_text': example, 'is_explanation': False }
                            ExampleModel.objects.create(**kwargs)

                    words_added += 1
                except Exception as e:
                    # Handle duplicates - check if it's a unique constraint violation
                    if "duplicate key value violates unique constraint" in str(e):
                        words_skipped += 1
                        logger.info(f"Skipping duplicate word: {word_data.get('noun_form') or word_data.get('verb_form') or word_data.get('adjective_form') or word_data.get('adverb_form')}")
                    else:
                        # Re-raise other exceptions
                        raise
        
        # Create appropriate message
        permanently_failed = processor.get_permanently_failed_batches()
        
        if permanently_failed:
            failed_count = len(permanently_failed)
            request.session['message'] = f"Added {words_added} words ({words_skipped} duplicates skipped). Warning: {failed_count} batch(es) failed after 3 attempts."
            request.session['success'] = words_added > 0
        elif words_added > 0 and words_skipped > 0:
            request.session['message'] = f"Successfully added {words_added} words. {words_skipped} duplicate words were skipped."
            request.session['success'] = True
        elif words_added > 0:
            lang_label = 'French' if language == 'french' else 'Spanish' if language == 'spanish' else 'Words'
            request.session['message'] = f"Successfully added {words_added} {lang_label.lower()} words."
            request.session['success'] = True
        elif words_skipped > 0:
            request.session['message'] = f"No new words added. {words_skipped} duplicate words were skipped."
            request.session['success'] = False
        else:
            # Preserve error message from processing summary
            request.session['message'] = message if not success else "No words were processed."
            request.session['success'] = success
    
    except Exception as e:
        logger.error(f"Error processing text: {str(e)}")
        logger.error(traceback.format_exc())
        request.session['message'] = f"An error occurred: {str(e)}"
        request.session['success'] = False
    
    # Redirect back with the same provider and active tab
    active_lang = 'es' if language == 'spanish' else ('it' if language == 'italian' else ('ru' if language == 'russian' else ('ja' if language == 'japanese' else 'fr')))
    return redirect(reverse('french_words') + f'?provider={provider}&lang={active_lang}')

def view_ai_response(request):
    """View to display the latest AI response details for debugging"""
    # Check if we have a latest response in the session
    if 'latest_ai_response' not in request.session:
        return render(request, 'words/ai_response.html', {
            'error': 'No AI response found. Try processing some text first.'
        })
    
    # Get the response data from session
    response_data = request.session['latest_ai_response']
    
    # Get preprocessing and batch details if available
    preprocessing_details = request.session.get('preprocessing_details', None)
    batch_details = request.session.get('batch_details', None)
    
    return render(request, 'words/ai_response.html', {
        'response': response_data,
        'response_json': json.dumps(response_data['raw_response'], indent=2),
        'preprocessing_details': preprocessing_details,
        'batch_details': batch_details
    })

@require_POST
def delete_record(request):
    """Delete a record by ID with support for cascade deletion"""
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        record_id = data.get('id')
        
        # Log the request data for debugging
        logger.info(f"Delete record request: model={model_name}, id={record_id}")
        
        # Validate input
        if not model_name or not record_id:
            return JsonResponse({'success': False, 'message': 'Model name and record ID are required'})
        
        # Get the model class dynamically
        try:
            model_class = apps.get_model('words', model_name)
        except LookupError:
            return JsonResponse({'success': False, 'message': f'Model {model_name} not found'})
        
        # We'll let DataService handle all related records, including examples
        # The special handling for FrenchWord examples is already in DataService.delete_by_id
        
        # Delete the record
        success, result = DataService.delete_by_id(model_class, record_id)
        
        if success:
            # Store operation ID for potential undo
            request.session['last_operation_id'] = result
            message = f'{model_name} with ID {record_id} was deleted successfully'
            if model_name == 'FrenchWord':
                message += f' along with its examples'
            return JsonResponse({'success': True, 'message': message, 'operation_id': result})
        else:
            return JsonResponse({'success': False, 'message': result})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in delete_record: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def delete_by_field(request):
    """Delete records by a specific field value (such as foreign key)"""
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        field_name = data.get('field')
        field_value = data.get('value')
        delete_parent = data.get('delete_parent', False)
        
        # Validate input
        if not model_name or not field_name or field_value is None:
            return JsonResponse({'success': False, 'message': 'Model name, field name, and field value are required'})
        
        # Get the model class dynamically
        try:
            model_class = apps.get_model('words', model_name)
        except LookupError:
            return JsonResponse({'success': False, 'message': f'Model {model_name} not found'})
        
        # Delete records by field value
        success, result, count = DataService.delete_by_field_value(model_class, field_name, field_value, delete_parent)
        
        if success:
            # Store operation ID for potential undo
            request.session['last_operation_id'] = result
            return JsonResponse({
                'success': True, 
                'message': f'Deleted {count} {model_name} records with {field_name}={field_value}', 
                'operation_id': result,
                'count': count
            })
        else:
            return JsonResponse({'success': False, 'message': result})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in delete_by_field: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def get_field_choices_ajax(request):
    """Get the available field choices for a model"""
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        
        if not model_name:
            return JsonResponse({'success': False, 'message': 'Model name is required'})
        
        fields = get_field_choices(model_name)
        
        return JsonResponse({
            'success': True,
            'fields': fields
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in get_field_choices_ajax: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def delete_record_range(request):
    """Delete records within an ID range"""
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        start_id = data.get('start_id')
        end_id = data.get('end_id')
        
        # Log the request data for debugging
        logger.info(f"Delete record range request: model={model_name}, range={start_id}-{end_id}")
        
        # Validate input
        if not model_name or start_id is None or end_id is None:
            return JsonResponse({'success': False, 'message': 'Model name, start ID, and end ID are required'})
        
        # Convert to integers
        try:
            start_id = int(start_id)
            end_id = int(end_id)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Start ID and end ID must be integers'})
        
        # Ensure start_id <= end_id
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        
        # Get the model class dynamically
        try:
            model_class = apps.get_model('words', model_name)
        except LookupError:
            return JsonResponse({'success': False, 'message': f'Model {model_name} not found'})
            
        # We'll let DataService handle all related records, including examples
        # The special handling for FrenchWord examples is in DataService.delete_by_id_range
        examples_count = 0
                
        # Delete the records
        success, result, count = DataService.delete_by_id_range(model_class, start_id, end_id)
        
        if success:
            # Store operation ID for potential undo
            request.session['last_operation_id'] = result
            message = f'{count} {model_name} records were deleted successfully'
            if model_name == 'FrenchWord':
                message += f' along with {examples_count} examples'
            return JsonResponse({'success': True, 'message': message, 'operation_id': result})
        else:
            return JsonResponse({'success': False, 'message': result})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in delete_record_range: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def delete_all_records(request):
    """Delete all records of a specific model"""
    try:
        data = json.loads(request.body)
        model_name = data.get('model')
        
        # Log the request data for debugging
        logger.info(f"Delete all records request: model={model_name}")
        
        # Validate input
        if not model_name:
            return JsonResponse({'success': False, 'message': 'Model name is required'})
        
        # Get the model class dynamically
        try:
            model_class = apps.get_model('words', model_name)
        except LookupError:
            return JsonResponse({'success': False, 'message': f'Model {model_name} not found'})
            
        # We'll let DataService handle all related records, including examples
        # The special handling for FrenchWord examples is in DataService.delete_all
        examples_count = 0
        
        # Delete all records
        success, result, count = DataService.delete_all(model_class)
        
        if success:
            # Store operation ID for potential undo
            request.session['last_operation_id'] = result
            message = f'All {count} {model_name} records were deleted successfully'
            if model_name == 'FrenchWord':
                message += f' along with {examples_count} examples'
            return JsonResponse({'success': True, 'message': message, 'operation_id': result})
        else:
            return JsonResponse({'success': False, 'message': result})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in delete_all_records: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def undo_last_deletion(request):
    """Undo the last deletion operation"""
    try:
        # Get the operation ID from the request body
        data = json.loads(request.body)
        operation_id = data.get('operation_id')
        
        # If not provided, try to get from session
        if not operation_id:
            operation_id = request.session.get('last_operation_id')
            
        # Validate input
        if not operation_id:
            return JsonResponse({'success': False, 'message': 'No previous deletion operation found'})
        
        # Undo the deletion
        success, message, count = DataService.undo_deletion(operation_id)
        
        if success:
            # Clear the operation ID from session
            if 'last_operation_id' in request.session:
                del request.session['last_operation_id']
            return JsonResponse({'success': True, 'message': message})
        else:
            return JsonResponse({'success': False, 'message': message})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in undo_last_deletion: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
def toggle_marked_for_review(request):
    """Toggle the marked_for_review field for a FrenchWord"""
    try:
        data = json.loads(request.body)
        word_id = data.get('id')
        
        if not word_id:
            return JsonResponse({'success': False, 'message': 'Word ID is required'})
        
        try:
            # Get the word
            word = FrenchWord.objects.get(id=word_id)
            
            # Toggle the flag
            word.marked_for_review = not word.marked_for_review
            word.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Word {word_id} {"marked" if word.marked_for_review else "unmarked"} for review',
                'marked': word.marked_for_review
            })
        except FrenchWord.DoesNotExist:
            return JsonResponse({'success': False, 'message': f'FrenchWord with ID {word_id} not found'})
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in toggle_marked_for_review: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

def processing_status(request):
    """
    Return the current processing status as JSON.
    This endpoint is called via AJAX to update the UI during batch processing.
    """
    # Get processing info from session
    processing_info = request.session.get('processing_info', {})
    
    # Check if processing is active
    is_processing = bool(processing_info) and processing_info.get('status') == 'processing'
    
    # Default response
    response = {
        'is_processing': is_processing,
        'total_batches': processing_info.get('total_batches', 0),
        'completed_batches': processing_info.get('completed_batches', 0),
        'current_batch': processing_info.get('current_batch', '-'),
        'start_time': processing_info.get('start_time', ''),
        'status': processing_info.get('status', 'idle'),
        'batch_times': processing_info.get('batch_times', []),
        'end_time': processing_info.get('end_time', ''),
        'total_duration': processing_info.get('total_duration', None),
    }
    
    return JsonResponse(response)

@require_POST
def stop_processing(request):
    """
    Signal the running batch processor to stop after the current batch.
    Uses a cache flag keyed by the user's session to communicate with the worker loop.
    """
    try:
        # Ensure the session has a key
        if not request.session.session_key:
            request.session.save()
        key = f"processing_stop_{request.session.session_key}"
        cache.set(key, True, timeout=3600)

        # Update visible status to indicate stopping
        if 'processing_info' in request.session:
            request.session['processing_info']['status'] = 'stopping'
            request.session.modified = True
            try:
                request.session.save()
            except Exception:
                pass

        return JsonResponse({'success': True, 'message': 'Stopping requested'})
    except Exception as e:
        logger.error(f"Error in stop_processing: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

def word_detail(request, word_id):
    """
    Display details for a specific word.
    
    Args:
        request: HTTP request
        word_id: ID of the word to display
    """
    try:
        # Get the word from the database
        word = FrenchWord.objects.get(id=word_id)
        
        # Render the word detail template
        return render(request, 'words/word_detail.html', {
            'word': word,
        })
    except FrenchWord.DoesNotExist:
        # Word not found
        messages.error(request, f"Word with ID {word_id} not found")
        return redirect('french_words')
    except Exception as e:
        # Other errors
        logger.error(f"Error in word_detail: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('french_words')

def delete_word(request, word_id):
    """
    Delete a specific word.
    
    Args:
        request: HTTP request
        word_id: ID of the word to delete
    """
    try:
        # Get the word from the database
        word = FrenchWord.objects.get(id=word_id)
        
        # Store the word for the success message
        word_text = word.word
        
        # Delete the word
        word.delete()
        
        # Show success message
        messages.success(request, f"Word '{word_text}' deleted successfully")
        
    except FrenchWord.DoesNotExist:
        # Word not found
        messages.error(request, f"Word with ID {word_id} not found")
    except Exception as e:
        # Other errors
        logger.error(f"Error in delete_word: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
    
    # Redirect back to the word list
    return redirect('french_words')

def delete_all_words(request):
    """
    Delete all words from the database.
    """
    if request.method == 'POST':
        try:
            # Count words before deletion
            count = FrenchWord.objects.count()
            
            # Delete all words
            FrenchWord.objects.all().delete()
            
            # Show success message
            messages.success(request, f"All {count} words deleted successfully")
        except Exception as e:
            # Other errors
            logger.error(f"Error in delete_all_words: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
    
    # Redirect back to the word list
    return redirect('french_words')

def export_words(request):
    """
    Export all words to a CSV file.
    """
    try:
        # Create the HttpResponse object with CSV header
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="french_words_export.csv"'
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow(['Word', 'Definition', 'Synonyms', 'Antonyms', 'Examples', 'Explanation', 'Language', 'Marked for Review'])
        
        # Get all words
        words = FrenchWord.objects.all().order_by('word')
        
        # Write data rows
        for word in words:
            writer.writerow([
                word.word,
                word.definition,
                word.synonyms,
                word.antonyms,
                word.examples,
                word.explanation,
                word.language,
                'Yes' if word.marked_for_review else 'No'
            ])
        
        return response
    except Exception as e:
        # Log error
        logger.error(f"Error in export_words: {str(e)}")
        messages.error(request, f"Error exporting words: {str(e)}")
        return redirect('french_words')

def import_words(request):
    """
    Import words from a CSV file.
    """
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            csv_file = request.FILES['csv_file']
            
            # Check if file is CSV
            if not csv_file.name.endswith('.csv'):
                messages.error(request, "Please upload a CSV file")
                return redirect('french_words')
            
            # Decode and process CSV
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            
            # Import counts
            imported_count = 0
            skipped_count = 0
            
            # Process each row
            for row in reader:
                # Skip if word is missing
                if not row.get('Word'):
                    skipped_count += 1
                    continue
                
                # Create or update word
                word, created = FrenchWord.objects.update_or_create(
                    word=row.get('Word'),
                    language=row.get('Language', 'french'),
                    defaults={
                        'definition': row.get('Definition', ''),
                        'synonyms': row.get('Synonyms', ''),
                        'antonyms': row.get('Antonyms', ''),
                        'examples': row.get('Examples', ''),
                        'explanation': row.get('Explanation', ''),
                        'marked_for_review': row.get('Marked for Review', '').lower() == 'yes'
                    }
                )
                
                imported_count += 1
            
            # Show success message
            messages.success(request, f"Successfully imported {imported_count} words. Skipped {skipped_count} rows.")
        except Exception as e:
            # Log error
            logger.error(f"Error in import_words: {str(e)}")
            messages.error(request, f"Error importing words: {str(e)}")
    
    # Redirect back to the word list
    return redirect('french_words')

def translate_text(request, text):
    """
    Redirect to Google Translate for the given text.
    
    Args:
        request: HTTP request
        text: Text to translate
    """
    # Get language from query parameters, default to French
    language = request.GET.get('language', 'fr')
    
    # Create Google Translate URL
    translate_url = f"https://translate.google.com/?sl={language}&tl=en&text={text}&op=translate"
    
    # Redirect to Google Translate
    return redirect(translate_url)

@require_POST
def run_migration_batch(request):
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else request.POST
        batch_id = data.get('batch_id')
        provider = data.get('provider')
        model = data.get('model')
        if not batch_id:
            return JsonResponse({'success': False, 'message': 'batch_id required'})
        batch = MigrationBatch.objects.get(id=batch_id)
        batch.status = 'running'
        batch.save(update_fields=['status'])

        # Initialize processing info for UI (cache) similar to French page
        proc_key = f"migration_proc_{batch.id}"
        processing_info = {
            'total_items': MigrationItem.objects.filter(batch=batch).count(),
            'processed_items': 0,
            'status': 'processing',
            'start_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': '',
            'items': []  # list of {id, src, tgt, status, start, end, duration, error}
        }
        cache.set(proc_key, processing_info, timeout=24*3600)

        items = list(MigrationItem.objects.filter(batch=batch, status__in=['pending','failed']).order_by('id'))
        processed = 0
        batch_size = 20
        # Group items by (source_language, target_language) for batch translation
        groups_by_pair = {}
        for it in items:
            groups_by_pair.setdefault((it.source_language, it.target_language), []).append(it)

        for (src_lang, tgt_lang), lst in groups_by_pair.items():
            for i in range(0, len(lst), batch_size):
                chunk = lst[i:i+batch_size]
                # Build batch inputs and push prompts to cache pre-call
                batch_inputs = []
                for it in chunk:
                    ij = build_input_json(it.source_language, it.target_language, it.source_word_id)
                    batch_inputs.append({
                        'source_word_id': it.source_word_id,
                        'source_language': it.source_language,
                        'target_language': it.target_language,
                        'word': ij.get('word', {}),
                        'examples': ij.get('examples', []),
                    })
                # Build and cache prompts immediately for each item
                try:
                    from .migration_ai import build_batch_system_prompt, build_batch_user_prompt
                    system_prompt = build_batch_system_prompt(src_lang, tgt_lang)
                    user_prompt = build_batch_user_prompt(batch_inputs)
                    debug_key = f"migration_debug_{batch.id}"
                    d = cache.get(debug_key, [])
                    for it in chunk:
                        d.append({
                            'item_id': it.id,
                            'source_language': it.source_language,
                            'source_word_id': it.source_word_id,
                            'target_language': it.target_language,
                            'status': 'queued',
                            'system_prompt': system_prompt,
                            'user_prompt': user_prompt,
                        })
                    cache.set(debug_key, d, timeout=24*3600)
                except Exception:
                    pass

                # Time the batch call
                batch_start = datetime.datetime.now()
                try:
                    result = translate_batch_with_provider(provider, model, batch_inputs, src_lang, tgt_lang)
                except Exception as e:
                    # mark all items in chunk failed
                    for it in chunk:
                        it.status = 'failed'
                        it.error = str(e)
                        it.save(update_fields=['status','error','updated_at'])
                        # processing info update
                        pi = cache.get(proc_key) or processing_info
                        processed += 1
                        pi['processed_items'] = processed
                        pi['items'].append({
                            'id': it.id,
                            'src': f"{it.source_language}:{it.source_word_id}",
                            'tgt': it.target_language,
                            'status': it.status,
                            'start': batch_start.strftime('%Y-%m-%d %H:%M:%S'),
                            'end': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'duration': (datetime.datetime.now() - batch_start).total_seconds(),
                            'error': it.error,
                        })
                        cache.set(proc_key, pi, timeout=24*3600)
                    continue

                # Map results by source_word_id (prompt guarantees an array of objects)
                results_map = {}
                if isinstance(result, list):
                    for r in result:
                        sid = r.get('source_word_id')
                        if sid is not None:
                            results_map[int(sid)] = r
                elif isinstance(result, dict) and isinstance(result.get('results'), list):
                    for r in result['results']:
                        sid = r.get('source_word_id')
                        if sid is not None:
                            results_map[int(sid)] = r

                # Persist per-item results
                for it in chunk:
                    start_ts = batch_start
                    end_ts = datetime.datetime.now()
                    try:
                        ai_out = results_map.get(it.source_word_id)
                        if not ai_out:
                            raise RuntimeError('Batch response missing result for source_word_id')

                        # Find/create target word
                        target_word_id, created = find_or_create_target_word(it.target_language, ai_out)
                        # Link group
                        ensure_group_link(it.source_language, it.source_word_id, it.target_language, target_word_id)
                        # Insert examples
                        insert_target_examples(it.target_language, target_word_id, ai_out.get('examples'))
                        # Update item
                        it.target_word_id = target_word_id
                        it.status = 'created' if created else 'linked'
                        it.error = None
                        it.save(update_fields=['target_word_id','status','error','updated_at'])
                        status_now = it.status
                        error_now = None
                    except Exception as e:
                        it.status = 'failed'
                        it.error = str(e)
                        it.save(update_fields=['status','error','updated_at'])
                        status_now = 'failed'
                        error_now = str(e)
                    # update processing info
                    pi = cache.get(proc_key) or processing_info
                    processed += 1
                    pi['processed_items'] = processed
                    pi['items'].append({
                        'id': it.id,
                        'src': f"{it.source_language}:{it.source_word_id}",
                        'tgt': it.target_language,
                        'status': status_now,
                        'start': start_ts.strftime('%Y-%m-%d %H:%M:%S'),
                        'end': end_ts.strftime('%Y-%m-%d %H:%M:%S'),
                        'duration': (end_ts - start_ts).total_seconds(),
                        'error': error_now,
                    })
                    cache.set(proc_key, pi, timeout=24*3600)
        batch.status = 'completed'
        batch.save(update_fields=['status'])
        # finalize processing info
        pi = cache.get(proc_key) or processing_info
        pi['status'] = 'completed'
        pi['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cache.set(proc_key, pi, timeout=24*3600)
        return JsonResponse({'success': True, 'processed': processed})
    except Exception as e:
        logger.exception('Failed running migration batch')
        return JsonResponse({'success': False, 'message': str(e)})


def migration_status(request, batch_id: int):
    try:
        batch = MigrationBatch.objects.get(id=batch_id)
        total = MigrationItem.objects.filter(batch=batch).count()
        done = MigrationItem.objects.filter(batch=batch, status__in=['created','linked','skipped']).count()
        failed = MigrationItem.objects.filter(batch=batch, status='failed').count()
        debug_key = f"migration_debug_{batch_id}"
        debug_entries = cache.get(debug_key, [])
        proc_key = f"migration_proc_{batch_id}"
        processing_info = cache.get(proc_key, {})
        return JsonResponse({'success': True, 'batch': batch_id, 'status': batch.status, 'total': total, 'done': done, 'failed': failed, 'debug': debug_entries, 'processing': processing_info})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
