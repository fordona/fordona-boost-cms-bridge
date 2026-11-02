"""Synthetic ``[DEMO]`` questions for thin lessons in the Boost stub (plan §4.5, §4.6).

Six variants. Together they demonstrate every block type of plan §4.6 (text,
image, an image option, lottie and video_loop animations, video with captions,
audio with a transcript, rule cards of both kinds), each in a place §4.6 allows
it. A thin lesson always receives at least six synthetic questions (it has at
most two real ones and is topped up to eight), and its variants are consecutive,
so any one thin lesson shows every block type.

Each record is complete: both locales' prompt and options, the correct option
and the per-locale explanation, so the stub can serve delivery and grading for
it (synthetic ids are answered from ``synthetic.json``, never from Boost).

Asset ids are placeholders under ``demo/``. The sample files themselves live in
the dev media bucket (plan §4.5), which is provisioned outside this repository.
"""

from typing import Any

Blocks = list[dict[str, Any]]

LOCALES = ("sv-SE", "en-GB")


def _text(markdown: str) -> dict[str, Any]:
    return {"type": "text", "markdown": markdown}


def _image(
    asset: str, alt: str, *, width: int | None = None, height: int | None = None
) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "image", "assetId": f"demo/{asset}", "alt": alt}
    if width and height:
        block.update(width=width, height=height)
    return block


def _option(option_id: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"id": option_id, "blocks": list(blocks)}


def _text_options(*texts: str) -> list[dict[str, Any]]:
    return [_option(chr(ord("a") + n), _text(t)) for n, t in enumerate(texts)]


def _variant_image_prompt(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text(
            "[DEMO] Du kör ut från en parkering. Vem ska du lämna företräde åt?"
            if sv
            else "[DEMO] You are leaving a car park. Who must you give way to?"
        ),
        _image(
            "car-park-exit",
            "Utfart från parkering" if sv else "Car park exit",
            width=1440,
            height=810,
        ),
    ]
    options = _text_options(
        *(
            ("Ingen", "Fordon från höger", "Alla fordon och gående på vägen")
            if sv
            else ("Nobody", "Vehicles from the right", "All vehicles and pedestrians on the road")
        )
    )
    explanation = [
        _text(
            "När du kör ut från en parkering har du väjningsplikt mot alla."
            if sv
            else "When leaving a car park you must give way to everyone."
        ),
        {
            "type": "rule_card",
            "kind": "RULE",
            "title": "Utfartsregeln" if sv else "The exit rule",
            "points": [
                "Lämna företräde åt alla trafikanter." if sv else "Give way to all road users."
            ],
        },
    ]
    return prompt, options, explanation


def _variant_sign_options(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text(
            "[DEMO] Vilket märke betyder väjningsplikt?"
            if sv
            else "[DEMO] Which sign means give way?"
        ),
        {
            "type": "animation",
            "assetId": "demo/give-way-lottie",
            "format": "lottie",
            "alt": "Animerad korsning" if sv else "Animated junction",
        },
    ]
    options = [
        _option("a", _image("sign-stop", "Stoppskylt" if sv else "Stop sign")),
        _option("b", _image("sign-give-way", "Väjningspliktsskylt" if sv else "Give-way sign")),
        _option("c", _image("sign-no-entry", "Förbud mot infart" if sv else "No entry sign")),
    ]
    explanation = [
        _text(
            "Den triangulära skylten med röd kant betyder väjningsplikt."
            if sv
            else "The triangular sign with a red border means give way."
        ),
        {
            "type": "rule_card",
            "kind": "SIGN",
            "title": "Väjningsplikt" if sv else "Give way",
            "points": ["Sakta in och lämna företräde." if sv else "Slow down and give way."],
            "image": {
                "assetId": "demo/sign-give-way",
                "alt": "Väjningspliktsskylt" if sv else "Give-way sign",
            },
        },
    ]
    return prompt, options, explanation


def _variant_video_prompt(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text(
            "[DEMO] Titta på filmen. Vad gjorde föraren fel?"
            if sv
            else "[DEMO] Watch the video. What did the driver do wrong?"
        ),
        {
            "type": "video",
            "assetId": "demo/roundabout-video",
            "posterAssetId": "demo/roundabout-poster",
            "durationSec": 42,
            "captions": [
                {"locale": loc, "assetId": f"demo/roundabout-{loc}.vtt"} for loc in LOCALES
            ],
        },
    ]
    options = _text_options(
        *(
            ("Blinkade inte ut", "Körde för sakta", "Inget")
            if sv
            else ("Did not signal on exit", "Drove too slowly", "Nothing")
        )
    )
    explanation = [
        _text(
            "Du ska blinka höger innan du lämnar cirkulationsplatsen."
            if sv
            else "Signal right before you leave the roundabout."
        ),
        {
            "type": "animation",
            "assetId": "demo/roundabout-loop",
            "format": "video_loop",
            "alt": "Bil som blinkar ut" if sv else "Car signalling on exit",
        },
    ]
    return prompt, options, explanation


def _variant_audio_prompt(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text(
            "[DEMO] Lyssna på klippet. Vilket fordon hörs?"
            if sv
            else "[DEMO] Listen to the clip. Which vehicle can you hear?"
        ),
        {
            "type": "audio",
            "assetId": "demo/siren-audio",
            "durationSec": 12,
            "transcript": "En utryckningssiren närmar sig."
            if sv
            else "An emergency siren approaching.",
        },
    ]
    options = _text_options(
        *(
            ("Utryckningsfordon", "Tåg", "Motorcykel")
            if sv
            else ("Emergency vehicle", "Train", "Motorcycle")
        )
    )
    explanation = [
        _text(
            "Släpp fram utryckningsfordon med påslagna signaler."
            if sv
            else "Let emergency vehicles with sirens on pass."
        ),
        _image("pull-over", "Bil som kör åt sidan" if sv else "Car pulling over"),
    ]
    return prompt, options, explanation


def _variant_true_false(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text(
            "[DEMO] Sant eller falskt: du får köra om i en korsning."
            if sv
            else "[DEMO] True or false: you may overtake in a junction."
        ),
        {
            "type": "animation",
            "assetId": "demo/overtake-loop",
            "format": "video_loop",
            "alt": "Omkörning i korsning" if sv else "Overtaking in a junction",
        },
    ]
    options = _text_options(*(("Sant", "Falskt") if sv else ("True", "False")))
    explanation = [
        _text(
            "Omkörning i korsning är som huvudregel förbjuden."
            if sv
            else "Overtaking in a junction is generally prohibited."
        ),
    ]
    return prompt, options, explanation


def _variant_mixed_options(locale: str) -> tuple[Blocks, list[dict[str, Any]], Blocks]:
    sv = locale == "sv-SE"
    prompt = [
        _text("[DEMO] Vad gäller vid denna skylt?" if sv else "[DEMO] What applies at this sign?"),
    ]
    options = [
        _option(
            "a",
            _text("Parkering förbjuden" if sv else "No parking"),
            _image("sign-no-parking", "Parkering förbjuden" if sv else "No parking sign"),
        ),
        _option("b", _text("Stannande förbjudet" if sv else "No stopping")),
        _option("c", _text("Huvudled" if sv else "Priority road")),
    ]
    explanation = [
        _text(
            "Skylten förbjuder parkering men tillåter stannande."
            if sv
            else "The sign forbids parking but allows stopping."
        ),
        {
            "type": "video",
            "assetId": "demo/parking-video",
            "posterAssetId": "demo/parking-poster",
            "durationSec": 30,
            "captions": [{"locale": loc, "assetId": f"demo/parking-{loc}.vtt"} for loc in LOCALES],
        },
    ]
    return prompt, options, explanation


# (builder, question type, difficulty, correct option id)
_CATALOGUE = (
    (_variant_image_prompt, "mcq", 1, "c"),
    (_variant_sign_options, "mcq", 2, "b"),
    (_variant_video_prompt, "mcq", 3, "a"),
    (_variant_audio_prompt, "mcq", 4, "a"),
    (_variant_true_false, "truefalse", 5, "b"),
    (_variant_mixed_options, "mcq", 3, "a"),
)
CATALOGUE_SIZE = len(_CATALOGUE)


def synthetic_question(
    *, lesson_id: str, module_id: str, subject_id: str | None, variant: int
) -> dict[str, Any]:
    """One synthetic question's content (everything but its id and version)."""
    builder, question_type, difficulty, correct = _CATALOGUE[variant % CATALOGUE_SIZE]
    translations: dict[str, Any] = {}
    explanation: dict[str, Blocks] = {}
    for locale in LOCALES:
        prompt, options, locale_explanation = builder(locale)
        translations[locale] = {"prompt": prompt, "options": options}
        explanation[locale] = locale_explanation
    return {
        "lessonId": lesson_id,
        "moduleId": module_id,
        "subjectId": subject_id,
        "difficulty": difficulty,
        "type": question_type,
        "topicKey": f"lesson-{lesson_id}",
        "variant": variant % CATALOGUE_SIZE,
        "translations": translations,
        "correctOptionId": correct,
        "explanation": explanation,
    }
