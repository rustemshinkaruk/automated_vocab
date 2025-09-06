import logging
from typing import Dict, Any, Tuple, Optional
from django.db import transaction
from django.db.models import Model
from django.core.cache import cache
from .models import (
    MigrationBatch, MigrationItem, LexemeGroup, LexemeGroupMember,
    FrenchWord, SpanishWord, ItalianWord, RussianWord, JapaneseWord,
    FrenchExample, SpanishExample, ItalianExample, RussianExample, JapaneseExample
)
from .migration_ai import translate_with_provider, build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

LANG_TO_WORDMODEL = {
    'fr': FrenchWord,
    'es': SpanishWord,
    'it': ItalianWord,
    'ru': RussianWord,
    'ja': JapaneseWord,
}

LANG_TO_EXAMPLEMODEL = {
    'fr': FrenchExample,
    'es': SpanishExample,
    'it': ItalianExample,
    'ru': RussianExample,
    'ja': JapaneseExample,
}


def build_input_json(source_lang: str, target_lang: str, source_word_id: int) -> Dict[str, Any]:
    WordModel: Model = LANG_TO_WORDMODEL[source_lang]
    word = WordModel.objects.get(id=source_word_id)

    # Fetch examples explicitly by language
    if source_lang == 'fr':
        examples = list(FrenchExample.objects.filter(french_word=word).values('id', 'example_text'))
    elif source_lang == 'es':
        examples = list(SpanishExample.objects.filter(spanish_word=word).values('id', 'example_text'))
    elif source_lang == 'it':
        examples = list(ItalianExample.objects.filter(italian_word=word).values('id', 'example_text'))
    elif source_lang == 'ru':
        examples = list(RussianExample.objects.filter(russian_word=word).values('id', 'example_text'))
    elif source_lang == 'ja':
        examples = list(JapaneseExample.objects.filter(japanese_word=word).values('id', 'example_text'))
    else:
        examples = []

    input_json = {
        'source_language': source_lang,
        'target_language': target_lang,
        'word': {
            'id': word.id,
            'lemma': word.word if hasattr(word, 'word') else None,
            'forms': {
                'noun': getattr(word, 'noun_form', '') or '',
                'verb': getattr(word, 'verb_form', '') or '',
                'adjective': getattr(word, 'adjective_form', '') or '',
                'adverb': getattr(word, 'adverb_form', '') or '',
            },
            'synonyms': [
                getattr(word, 'synonym_noun_form', '') or '',
                getattr(word, 'synonym_verb_form', '') or '',
                getattr(word, 'synonym_adjective_form', '') or '',
                getattr(word, 'synonym_adverb_form', '') or '',
            ],
            'antonyms': [
                getattr(word, 'antonym_noun_form', '') or '',
                getattr(word, 'antonym_verb_form', '') or '',
                getattr(word, 'antonym_adjective_form', '') or '',
                getattr(word, 'antonym_adverb_form', '') or '',
            ],
            'category': getattr(word, 'category', None),
            'frequency': getattr(word, 'frequency', None),
        },
        'examples': [
            {'id': e['id'], 'text': e['example_text']} for e in examples
        ]
    }
    # Clean empty strings from synonyms/antonyms lists
    input_json['word']['synonyms'] = [s for s in input_json['word']['synonyms'] if s]
    input_json['word']['antonyms'] = [s for s in input_json['word']['antonyms'] if s]
    return input_json


def find_or_create_target_word(target_lang: str, ai_out: Dict[str, Any]) -> Tuple[int, bool]:
    """
    Return (word_id, created_flag). Dedup primarily by lemma/forms.
    """
    WordModel: Model = LANG_TO_WORDMODEL[target_lang]
    lemma = ai_out.get('lemma') or ''
    forms = ai_out.get('forms', {})

    # Try exact matches across forms/lemma
    for field, key in [('noun_form', 'noun'), ('verb_form', 'verb'), ('adjective_form', 'adjective'), ('adverb_form', 'adverb')]:
        val = forms.get(key)
        if val:
            obj = WordModel.objects.filter(**{field: val}).first()
            if obj:
                return obj.id, False

    # Try lemma fallback across all form fields
    if lemma:
        for field in ['noun_form', 'verb_form', 'adjective_form', 'adverb_form']:
            obj = WordModel.objects.filter(**{field: lemma}).first()
            if obj:
                return obj.id, False

    # Create new
    obj = WordModel.objects.create(
        noun_form=forms.get('noun') or None,
        verb_form=forms.get('verb') or None,
        adjective_form=forms.get('adjective') or None,
        adverb_form=forms.get('adverb') or None,
        original_phrase=ai_out.get('lemma') or None,
        frequency=str(ai_out.get('metadata', {}).get('frequency') or ''),
        category=ai_out.get('metadata', {}).get('category') or None,
        native=False,
        explanation=ai_out.get('explanation') or None,
    )
    # Update synonyms/antonyms if present in AI output (supports both list and per-form mapping)
    syns = ai_out.get('synonyms')
    ants = ai_out.get('antonyms')
    if isinstance(syns, dict):
        obj.synonym_noun_form = syns.get('noun') or None
        obj.synonym_verb_form = syns.get('verb') or None
        obj.synonym_adjective_form = syns.get('adjective') or None
        obj.synonym_adverb_form = syns.get('adverb') or None
    elif isinstance(syns, list):
        # best-effort map by order if a flat list was returned
        for i, key in enumerate(['noun','verb','adjective','adverb']):
            try:
                val = syns[i]
            except Exception:
                val = None
            if key == 'noun': obj.synonym_noun_form = val or None
            if key == 'verb': obj.synonym_verb_form = val or None
            if key == 'adjective': obj.synonym_adjective_form = val or None
            if key == 'adverb': obj.synonym_adverb_form = val or None
    if isinstance(ants, dict):
        obj.antonym_noun_form = ants.get('noun') or None
        obj.antonym_verb_form = ants.get('verb') or None
        obj.antonym_adjective_form = ants.get('adjective') or None
        obj.antonym_adverb_form = ants.get('adverb') or None
    elif isinstance(ants, list):
        for i, key in enumerate(['noun','verb','adjective','adverb']):
            try:
                val = ants[i]
            except Exception:
                val = None
            if key == 'noun': obj.antonym_noun_form = val or None
            if key == 'verb': obj.antonym_verb_form = val or None
            if key == 'adjective': obj.antonym_adjective_form = val or None
            if key == 'adverb': obj.antonym_adverb_form = val or None
    obj.save(update_fields=[
        'synonym_noun_form','synonym_verb_form','synonym_adjective_form','synonym_adverb_form',
        'antonym_noun_form','antonym_verb_form','antonym_adjective_form','antonym_adverb_form','explanation'
    ])
    return obj.id, True


def ensure_group_link(source_lang: str, source_word_id: int, target_lang: str, target_word_id: int) -> int:
    """Put both words into a single LexemeGroup; return group_id."""
    # Find group for either member
    src_member = LexemeGroupMember.objects.filter(language=source_lang, word_id=source_word_id).first()
    tgt_member = LexemeGroupMember.objects.filter(language=target_lang, word_id=target_word_id).first()

    if src_member and tgt_member and src_member.group_id != tgt_member.group_id:
        # Merge: move all target members into source group, delete target group
        with transaction.atomic():
            old = tgt_member.group
            for m in LexemeGroupMember.objects.filter(group=old):
                LexemeGroupMember.objects.update_or_create(
                    language=m.language, word_id=m.word_id,
                    defaults={"group": src_member.group}
                )
            old.delete()
        return src_member.group_id

    group = src_member.group if src_member else (tgt_member.group if tgt_member else None)
    if not group:
        group = LexemeGroup.objects.create()
    LexemeGroupMember.objects.get_or_create(group=group, language=source_lang, word_id=source_word_id)
    LexemeGroupMember.objects.get_or_create(group=group, language=target_lang, word_id=target_word_id)
    return group.id


def insert_target_examples(target_lang: str, target_word_id: int, examples_out):
    ExampleModel: Model = LANG_TO_EXAMPLEMODEL[target_lang]
    WordModel: Model = LANG_TO_WORDMODEL[target_lang]
    word = WordModel.objects.get(id=target_word_id)
    for ex in examples_out or []:
        text = ex.get('text')
        if not text:
            continue
        if target_lang == 'fr':
            ExampleModel.objects.create(french_word=word, example_text=text)
        elif target_lang == 'es':
            ExampleModel.objects.create(spanish_word=word, example_text=text)
        elif target_lang == 'it':
            ExampleModel.objects.create(italian_word=word, example_text=text)
        elif target_lang == 'ru':
            ExampleModel.objects.create(russian_word=word, example_text=text)
        elif target_lang == 'ja':
            ExampleModel.objects.create(japanese_word=word, example_text=text)


def process_migration_item(item: MigrationItem, provider: str, model: str) -> None:
    with transaction.atomic():
        item.status = 'processing'
        item.save(update_fields=['status', 'updated_at'])
    try:
        input_json = build_input_json(item.source_language, item.target_language, item.source_word_id)
        # Build prompts for debug visibility (store regardless of success/failure)
        system_prompt = build_system_prompt(item.source_language, item.target_language)
        user_prompt = build_user_prompt(input_json)
        ai_out = translate_with_provider(provider, model, input_json)

        # Find or create target word
        target_word_id, created = find_or_create_target_word(item.target_language, ai_out)

        # Link in group
        ensure_group_link(item.source_language, item.source_word_id, item.target_language, target_word_id)

        # Insert examples
        insert_target_examples(item.target_language, target_word_id, ai_out.get('examples'))

        # Update item
        with transaction.atomic():
            item.target_word_id = target_word_id
            item.status = 'created' if created else 'linked'
            item.save(update_fields=['target_word_id', 'status', 'updated_at'])

        # Store debug info in cache for migrations page
        try:
            debug_key = f"migration_debug_{item.batch_id}"
            entries = cache.get(debug_key, [])
            entries.append({
                'item_id': item.id,
                'source_language': item.source_language,
                'source_word_id': item.source_word_id,
                'target_language': item.target_language,
                'status': item.status,
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'ai_result': ai_out,
            })
            cache.set(debug_key, entries, timeout=24*3600)
        except Exception:
            # Best-effort; do not break migration flow on cache issues
            pass
    except Exception as e:
        logger.exception('Migration item failed')
        with transaction.atomic():
            item.status = 'failed'
            item.error = str(e)
            item.save(update_fields=['status', 'error', 'updated_at'])
        # Store failure in cache as well, including prompts if available
        try:
            debug_key = f"migration_debug_{item.batch_id}"
            entries = cache.get(debug_key, [])
            entries.append({
                'item_id': item.id,
                'source_language': item.source_language,
                'source_word_id': item.source_word_id,
                'target_language': item.target_language,
                'status': 'failed',
                'error': str(e),
                'system_prompt': locals().get('system_prompt'),
                'user_prompt': locals().get('user_prompt'),
            })
            cache.set(debug_key, entries, timeout=24*3600)
        except Exception:
            pass
