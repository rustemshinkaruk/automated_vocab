from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('word_list/', views.word_list, name='word_list'),
    path('french_words/', views.french_words, name='french_words'),
    path('process-french-text/', views.process_french_text, name='process_french_text'),
    path('processing-status/', views.processing_status, name='processing_status'),
    path('stop_processing/', views.stop_processing, name='stop_processing'),
    path('word/<int:word_id>/', views.word_detail, name='word_detail'),
    path('delete-word/<int:word_id>/', views.delete_word, name='delete_word'),
    path('delete-all-words/', views.delete_all_words, name='delete_all_words'),
    path('export-words/', views.export_words, name='export_words'),
    path('import-words/', views.import_words, name='import_words'),
    path('translate/<str:text>/', views.translate_text, name='translate_text'),
    path('toggle_marked_for_review/', views.toggle_marked_for_review, name='toggle_marked_for_review'),
    path('delete_record/', views.delete_record, name='delete_record'),
    path('delete_record_range/', views.delete_record_range, name='delete_record_range'),
    path('delete_all_records/', views.delete_all_records, name='delete_all_records'),
    path('delete_by_field/', views.delete_by_field, name='delete_by_field'),
    path('undo_deletion/', views.undo_last_deletion, name='undo_deletion'),
    path('api/get_field_choices/', views.get_field_choices_ajax, name='get_field_choices_api'),
    path('ai_response/', views.view_ai_response, name='view_ai_response'),
    path('migrations/', views.migrations_page, name='migrations_page'),
    # New migration APIs
    path('api/migrations/models_for_provider/', views.api_models_for_provider, name='migration_models_for_provider'),
    path('api/migrations/start/', views.start_migration, name='start_migration'),
    path('api/migrations/run/', views.run_migration_batch, name='run_migration_batch'),
    path('api/migrations/status/<int:batch_id>/', views.migration_status, name='migration_status'),
] 