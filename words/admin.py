from django.contrib import admin
from .models import Word, FrenchWord, FrenchExample, SpanishWord, SpanishExample, ItalianWord, ItalianExample, RussianWord, RussianExample, JapaneseWord, JapaneseExample

@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ('english', 'spanish', 'french', 'russian', 'category_name', 'category_level', 'created_at')
    list_filter = ('category_name', 'category_level')
    search_fields = ('english', 'spanish', 'french', 'russian', 'category_name')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

@admin.register(FrenchWord)
class FrenchWordAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'created_at')
    search_fields = ('original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form')
    ordering = ('id',)
    date_hierarchy = 'created_at'

@admin.register(FrenchExample)
class FrenchExampleAdmin(admin.ModelAdmin):
    list_display = ('french_word', 'example_text', 'created_at')
    search_fields = ('example_text',)
    list_filter = ('french_word',)
    ordering = ('french_word', 'id')

@admin.register(SpanishWord)
class SpanishWordAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'created_at')
    search_fields = ('original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form')
    ordering = ('id',)
    date_hierarchy = 'created_at'

@admin.register(SpanishExample)
class SpanishExampleAdmin(admin.ModelAdmin):
    list_display = ('spanish_word', 'example_text', 'created_at')
    search_fields = ('example_text',)
    list_filter = ('spanish_word',)
    ordering = ('spanish_word', 'id')

@admin.register(ItalianWord)
class ItalianWordAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'created_at')
    search_fields = ('original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form')
    ordering = ('id',)
    date_hierarchy = 'created_at'

@admin.register(ItalianExample)
class ItalianExampleAdmin(admin.ModelAdmin):
    list_display = ('italian_word', 'example_text', 'created_at')
    search_fields = ('example_text',)
    list_filter = ('italian_word',)
    ordering = ('italian_word', 'id')

@admin.register(RussianWord)
class RussianWordAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'created_at')
    search_fields = ('original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form')
    ordering = ('id',)
    date_hierarchy = 'created_at'

@admin.register(RussianExample)
class RussianExampleAdmin(admin.ModelAdmin):
    list_display = ('russian_word', 'example_text', 'created_at')
    search_fields = ('example_text',)
    list_filter = ('russian_word',)
    ordering = ('russian_word', 'id')

@admin.register(JapaneseWord)
class JapaneseWordAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'kanji_form', 'kana_reading', 'romaji', 'created_at')
    search_fields = ('original_phrase', 'noun_form', 'verb_form', 'adjective_form', 'adverb_form', 'kanji_form', 'kana_reading', 'romaji')
    ordering = ('id',)
    date_hierarchy = 'created_at'

@admin.register(JapaneseExample)
class JapaneseExampleAdmin(admin.ModelAdmin):
    list_display = ('japanese_word', 'example_text', 'created_at')
    search_fields = ('example_text',)
    list_filter = ('japanese_word',)
    ordering = ('japanese_word', 'id')
