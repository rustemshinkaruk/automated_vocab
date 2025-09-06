import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def call_openai(system_prompt: str, user_prompt: str, model: str) -> Dict[str, Any]:
    import openai
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY is not set')
    client = openai.OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    text = resp.choices[0].message.content
    return _parse_json_strict(text)


def call_gemini(system_prompt: str, user_prompt: str, model: str) -> Dict[str, Any]:
    import google.generativeai as genai
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not set')
    genai.configure(api_key=api_key)
    normalized_model = model.split('/')[-1] if model else model
    gmodel = genai.GenerativeModel(normalized_model)
    prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    resp = gmodel.generate_content([{"role": "user", "parts": prompt}])
    text = resp.text
    return _parse_json_strict(text)


def call_anthropic(system_prompt: str, user_prompt: str, model: str) -> Dict[str, Any]:
    import anthropic
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY is not set')
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        system=system_prompt,
        max_tokens=2000,
        temperature=0.1,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = resp.content[0].text
    return _parse_json_strict(text)


def _parse_json_strict(text: str) -> Dict[str, Any]:
    # Try to extract JSON from possible code fences
    if '```' in text:
        # Prefer ```json fences
        if '```json' in text:
            part = text.split('```json', 1)[1].split('```', 1)[0]
            text = part
        else:
            part = text.split('```', 1)[1].split('```', 1)[0]
            text = part
    text = text.strip()
    return json.loads(text)


def build_system_prompt(source_lang: str, target_lang: str) -> str:
    return (
        "You are a bilingual lexicographer. Translate the provided JSON for a single source word and its examples "
        f"from {source_lang} to {target_lang}. Keep semantic fields aligned.\n\n"
        "Requirements:\n"
        "- Output STRICT JSON only; no commentary or markdown.\n"
        "- Match exactly the Target Output Schema keys and structure.\n"
        "- Do not add/remove items; keep counts equal to input where applicable.\n"
        "- Forms: noun/verb/adjective/adverb; use empty string if not applicable.\n"
        "- Frequency should be a string from this closed set: essential, very common, common, uncommon, rare, very rare.\n"
        "- Translate examples idiomatically; preserve meaning and register. Keep alignment by copying input example id to output source_example_id.\n"
        "- Translate the short explanation as well, keeping tone/register."
    )


def build_user_prompt(input_json: Dict[str, Any]) -> str:
    template = (
        "We are translating from {source_lang} to {target_lang}. Translate the following input JSON into the Target Output Schema.\n\n"
        "Input JSON:\n{input_block}\n\n"
        "Target Output Schema (produce exactly this shape):\n"
        "{{\n  \"lemma\": \"...\",\n  \"forms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"synonyms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"antonyms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"examples\": [{{\"source_example_id\": 987, \"text\": \"...\"}}],\n"
        "  \"explanation\": \"...\",\n"
        "  \"metadata\": {{\"category\": \"food\", \"frequency\": \"common\", \"origin\": \"non-native\"}}\n}}\n\n"
        "Return only the JSON object matching Target Output Schema."
    )
    src = input_json.get('source_language')
    tgt = input_json.get('target_language')
    input_block = json.dumps(input_json, ensure_ascii=False, indent=2)
    return template.format(source_lang=src, target_lang=tgt, input_block=input_block)


def translate_with_provider(provider: str, model: str, input_json: Dict[str, Any]) -> Dict[str, Any]:
    source_lang = input_json.get('source_language')
    target_lang = input_json.get('target_language')
    system_prompt = build_system_prompt(source_lang, target_lang)
    user_prompt = build_user_prompt(input_json)

    if provider == 'OpenAI':
        return call_openai(system_prompt, user_prompt, model)
    if provider == 'Gemini':
        return call_gemini(system_prompt, user_prompt, model)
    if provider == 'Anthropic':
        return call_anthropic(system_prompt, user_prompt, model)
    raise RuntimeError(f'Unsupported provider: {provider}')


def build_batch_system_prompt(source_lang: str, target_lang: str) -> str:
    return (
        "You are a bilingual lexicographer. Translate the provided ARRAY of source words and their examples "
        f"from {source_lang} to {target_lang}. Keep alignment by source_word_id.\n\n"
        "Requirements:\n"
        "- Output STRICT JSON only; no commentary or markdown.\n"
        "- Return an array where each element corresponds to an input element and includes source_word_id.\n"
        "- Forms: noun/verb/adjective/adverb; use empty string if not applicable.\n"
        "- Frequency must be one of: essential, very common, common, uncommon, rare, very rare.\n"
        "- Translate examples and the short explanation idiomatically and preserve register."
    )


def build_batch_user_prompt(inputs: Any) -> str:
    template = (
        "We are translating a batch of words. Keep output aligned with input via source_word_id.\n"
        "Each element represents one source word with its forms and examples.\n\n"
        "Input ARRAY (each element is one word with examples):\n{input_block}\n\n"
        "Target Output ARRAY (each element must match this object shape):\n"
        "{{\n  \"source_word_id\": 123,\n  \"lemma\": \"...\",\n  \"forms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"synonyms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"antonyms\": {{\"noun\": \"\", \"verb\": \"\", \"adjective\": \"\", \"adverb\": \"\"}},\n"
        "  \"examples\": [{{\"source_example_id\": 987, \"text\": \"...\"}}],\n"
        "  \"explanation\": \"...\",\n"
        "  \"metadata\": {{\"category\": \"food\", \"frequency\": \"common\", \"origin\": \"non-native\"}}\n}}\n\n"
        "Return only the JSON array matching the target shape."
    )
    input_block = json.dumps(inputs, ensure_ascii=False, indent=2)
    return template.format(input_block=input_block)


def translate_batch_with_provider(provider: str, model: str, inputs: Any, source_lang: str, target_lang: str):
    system_prompt = build_batch_system_prompt(source_lang, target_lang)
    user_prompt = build_batch_user_prompt(inputs)
    if provider == 'OpenAI':
        return call_openai(system_prompt, user_prompt, model)
    if provider == 'Gemini':
        return call_gemini(system_prompt, user_prompt, model)
    if provider == 'Anthropic':
        return call_anthropic(system_prompt, user_prompt, model)
    raise RuntimeError(f'Unsupported provider: {provider}')
