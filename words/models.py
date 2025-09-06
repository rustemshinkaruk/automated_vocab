from django.db import models

# Create your models here.

class Word(models.Model):
    # Primary key is automatically created by Django as 'id'
    english = models.CharField(max_length=100)
    spanish = models.CharField(max_length=100, blank=True, null=True)
    french = models.CharField(max_length=100, blank=True, null=True)
    russian = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    category_name = models.CharField(max_length=50)
    category_level = models.CharField(max_length=50, blank=True, null=True)
    
    def __str__(self):
        return f"{self.english}, {self.spanish}, {self.french}, {self.russian}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Word'
        verbose_name_plural = 'Words'

class FrenchWord(models.Model):
    # Django will automatically create an 'id' field as primary key
    noun_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    verb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adjective_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adverb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    # New synonym fields
    synonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # New antonym fields
    antonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Existing fields
    original_phrase = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    marked_for_review = models.BooleanField(default=False)
    frequency = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    category_2 = models.CharField(max_length=100, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    native = models.BooleanField(default=True)
    
    def __str__(self):
        forms = [f for f in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form] if f]
        return " / ".join(forms)
        
    @property
    def word(self):
        """
        Return the most appropriate form to represent this word.
        This property helps with templates expecting a 'word' attribute.
        """
        # Try to use original phrase first if available
        if self.original_phrase:
            return self.original_phrase
        
        # Otherwise, use the first available form
        for form in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form]:
            if form:
                return form
                
        return "Unnamed word"  # Fallback
    
    class Meta:
        ordering = ['id']
        verbose_name = 'French Word'
        verbose_name_plural = 'French Words'
        # Additional constraint to ensure uniqueness
        constraints = [
            models.UniqueConstraint(
                fields=['noun_form'], 
                name='unique_noun_form',
                condition=models.Q(noun_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['verb_form'], 
                name='unique_verb_form',
                condition=models.Q(verb_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adjective_form'], 
                name='unique_adjective_form',
                condition=models.Q(adjective_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adverb_form'], 
                name='unique_adverb_form',
                condition=models.Q(adverb_form__isnull=False)
            ),
        ]

class FrenchExample(models.Model):
    french_word = models.ForeignKey(FrenchWord, on_delete=models.CASCADE, related_name='examples')
    example_text = models.TextField()
    is_explanation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.example_text[:50] + "..." if len(self.example_text) > 50 else self.example_text
    
    class Meta:
        ordering = ['-is_explanation', 'id']  # Show explanations first
        verbose_name = 'French Example'
        verbose_name_plural = 'French Examples'

class SpanishWord(models.Model):
    # Mirror of FrenchWord for Spanish
    noun_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    verb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adjective_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adverb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    # Synonyms
    synonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Antonyms
    antonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Meta
    original_phrase = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    marked_for_review = models.BooleanField(default=False)
    frequency = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    category_2 = models.CharField(max_length=100, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    native = models.BooleanField(default=True)

    def __str__(self):
        forms = [f for f in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form] if f]
        return " / ".join(forms)

    @property
    def word(self):
        if self.original_phrase:
            return self.original_phrase
        for form in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form]:
            if form:
                return form
        return "Unnamed word"

    class Meta:
        ordering = ['id']
        verbose_name = 'Spanish Word'
        verbose_name_plural = 'Spanish Words'
        constraints = [
            models.UniqueConstraint(
                fields=['noun_form'], name='unique_spanish_noun_form',
                condition=models.Q(noun_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['verb_form'], name='unique_spanish_verb_form',
                condition=models.Q(verb_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adjective_form'], name='unique_spanish_adjective_form',
                condition=models.Q(adjective_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adverb_form'], name='unique_spanish_adverb_form',
                condition=models.Q(adverb_form__isnull=False)
            ),
        ]

class SpanishExample(models.Model):
    spanish_word = models.ForeignKey(SpanishWord, on_delete=models.CASCADE, related_name='examples')
    example_text = models.TextField()
    is_explanation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.example_text[:50] + "..." if len(self.example_text) > 50 else self.example_text

    class Meta:
        ordering = ['-is_explanation', 'id']
        verbose_name = 'Spanish Example'
        verbose_name_plural = 'Spanish Examples'

class ItalianWord(models.Model):
    # Mirror of FrenchWord for Italian
    noun_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    verb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adjective_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adverb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    # Synonyms
    synonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Antonyms
    antonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Meta
    original_phrase = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    marked_for_review = models.BooleanField(default=False)
    frequency = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    category_2 = models.CharField(max_length=100, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    native = models.BooleanField(default=True)

    def __str__(self):
        forms = [f for f in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form] if f]
        return " / ".join(forms)

    @property
    def word(self):
        if self.original_phrase:
            return self.original_phrase
        for form in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form]:
            if form:
                return form
        return "Unnamed word"

    class Meta:
        ordering = ['id']
        verbose_name = 'Italian Word'
        verbose_name_plural = 'Italian Words'
        constraints = [
            models.UniqueConstraint(
                fields=['noun_form'], name='unique_italian_noun_form',
                condition=models.Q(noun_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['verb_form'], name='unique_italian_verb_form',
                condition=models.Q(verb_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adjective_form'], name='unique_italian_adjective_form',
                condition=models.Q(adjective_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adverb_form'], name='unique_italian_adverb_form',
                condition=models.Q(adverb_form__isnull=False)
            ),
        ]

class ItalianExample(models.Model):
    italian_word = models.ForeignKey(ItalianWord, on_delete=models.CASCADE, related_name='examples')
    example_text = models.TextField()
    is_explanation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.example_text[:50] + "..." if len(self.example_text) > 50 else self.example_text

    class Meta:
        ordering = ['-is_explanation', 'id']
        verbose_name = 'Italian Example'
        verbose_name_plural = 'Italian Examples'

class RussianWord(models.Model):
    # Mirror of FrenchWord for Russian
    noun_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    verb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adjective_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adverb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    # Synonyms
    synonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Antonyms
    antonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Meta
    original_phrase = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    marked_for_review = models.BooleanField(default=False)
    frequency = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    category_2 = models.CharField(max_length=100, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    native = models.BooleanField(default=True)

    def __str__(self):
        forms = [f for f in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form] if f]
        return " / ".join(forms)

    @property
    def word(self):
        if self.original_phrase:
            return self.original_phrase
        for form in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form]:
            if form:
                return form
        return "Unnamed word"

    class Meta:
        ordering = ['id']
        verbose_name = 'Russian Word'
        verbose_name_plural = 'Russian Words'
        constraints = [
            models.UniqueConstraint(
                fields=['noun_form'], name='unique_russian_noun_form',
                condition=models.Q(noun_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['verb_form'], name='unique_russian_verb_form',
                condition=models.Q(verb_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adjective_form'], name='unique_russian_adjective_form',
                condition=models.Q(adjective_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adverb_form'], name='unique_russian_adverb_form',
                condition=models.Q(adverb_form__isnull=False)
            ),
        ]

class RussianExample(models.Model):
    russian_word = models.ForeignKey(RussianWord, on_delete=models.CASCADE, related_name='examples')
    example_text = models.TextField()
    is_explanation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.example_text[:50] + "..." if len(self.example_text) > 50 else self.example_text

    class Meta:
        ordering = ['-is_explanation', 'id']
        verbose_name = 'Russian Example'
        verbose_name_plural = 'Russian Examples'

class JapaneseWord(models.Model):
    # Mirror of other language word models with extra script fields
    noun_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    verb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adjective_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    adverb_form = models.CharField(max_length=100, blank=True, null=True, unique=True)
    # Synonyms/Antonyms kept for parity (nullable)
    synonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    synonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_noun_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_verb_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adjective_form = models.CharField(max_length=100, blank=True, null=True)
    antonym_adverb_form = models.CharField(max_length=100, blank=True, null=True)
    # Existing
    original_phrase = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    marked_for_review = models.BooleanField(default=False)
    frequency = models.CharField(max_length=50, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    category_2 = models.CharField(max_length=100, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    native = models.BooleanField(default=True)
    # Japanese-specific script fields
    kanji_form = models.CharField(max_length=200, blank=True, null=True)
    kana_reading = models.CharField(max_length=200, blank=True, null=True)
    romaji = models.CharField(max_length=200, blank=True, null=True)
    furigana = models.TextField(blank=True, null=True)

    def __str__(self):
        forms = [f for f in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form] if f]
        return " / ".join(forms)

    @property
    def word(self):
        if self.original_phrase:
            return self.original_phrase
        for form in [self.noun_form, self.verb_form, self.adjective_form, self.adverb_form]:
            if form:
                return form
        return "Unnamed word"

    class Meta:
        ordering = ['id']
        verbose_name = 'Japanese Word'
        verbose_name_plural = 'Japanese Words'
        constraints = [
            models.UniqueConstraint(
                fields=['noun_form'], name='unique_japanese_noun_form',
                condition=models.Q(noun_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['verb_form'], name='unique_japanese_verb_form',
                condition=models.Q(verb_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adjective_form'], name='unique_japanese_adjective_form',
                condition=models.Q(adjective_form__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['adverb_form'], name='unique_japanese_adverb_form',
                condition=models.Q(adverb_form__isnull=False)
            ),
        ]

class JapaneseExample(models.Model):
    japanese_word = models.ForeignKey(JapaneseWord, on_delete=models.CASCADE, related_name='examples')
    example_text = models.TextField()
    is_explanation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.example_text[:50] + "..." if len(self.example_text) > 50 else self.example_text

    class Meta:
        ordering = ['-is_explanation', 'id']
        verbose_name = 'Japanese Example'
        verbose_name_plural = 'Japanese Examples'

class MigrationBatch(models.Model):
    """Tracks a migration run: source -> multiple targets."""
    created_at = models.DateTimeField(auto_now_add=True)
    source_language = models.CharField(max_length=8)
    target_languages = models.JSONField(default=list)  # list of codes like ["es","it"]
    status = models.CharField(max_length=32, default="created")  # created|running|completed|failed|stopped
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Batch {self.id} {self.source_language} -> {','.join(self.target_languages)} ({self.status})"

class MigrationItem(models.Model):
    """Tracks per-source word migration to one target language."""
    batch = models.ForeignKey(MigrationBatch, on_delete=models.CASCADE, related_name='items')
    source_language = models.CharField(max_length=8)
    source_word_id = models.PositiveBigIntegerField()
    target_language = models.CharField(max_length=8)
    status = models.CharField(max_length=32, default="pending")  # pending|processing|linked|created|skipped|failed
    target_word_id = models.PositiveBigIntegerField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "source_language", "source_word_id", "target_language"]),
        ]
        unique_together = ("batch", "source_language", "source_word_id", "target_language")

    def __str__(self):
        return f"Item src {self.source_language}:{self.source_word_id} -> {self.target_language} [{self.status}]"

class LexemeGroup(models.Model):
    """Represents an abstract concept grouping across languages."""
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"LexemeGroup {self.id}"

class LexemeGroupMember(models.Model):
    """Membership of a concrete language word in a lexeme group."""
    group = models.ForeignKey(LexemeGroup, on_delete=models.CASCADE, related_name='members')
    language = models.CharField(max_length=8)
    word_id = models.PositiveBigIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("language", "word_id")
        indexes = [
            models.Index(fields=["group", "language"]),
        ]

    def __str__(self):
        return f"Group {self.group_id} - {self.language}:{self.word_id}"
