"""AI Tutor — Response Structuring Engine (Phase 32).

INDEPENDENT of the knowledge-base system: this module is PURE (no DB, no network).
It takes the current question + chat context + student learning memory + approved-school
knowledge, and produces a structured system prompt + per-message observability metadata.
The server wires in DB access and the (mockable) LLM calls for the ambiguous-intent classify
and the post-response memory extraction. Knowledge, memory and model evolve separately.
"""
import re

# ---- Intents (section 2) ----
INTENTS = [
    "learn-concept", "factual", "solve-problem", "homework-help", "check-answer",
    "exam-prep", "revise", "practice", "example", "simpler-explanation",
    "follow-up", "correct-mistake",
]

# ---- Intent -> response strategy (section 10) ----
INTENT_STRATEGY = {
    "learn-concept": "concept_explanation",
    "factual": "factual_direct",
    "solve-problem": "problem_solving",
    "homework-help": "problem_solving",
    "check-answer": "answer_checking",
    "correct-mistake": "answer_checking",
    "exam-prep": "exam_prep",
    "revise": "revision",
    "practice": "practice",
    "example": "example",
    "simpler-explanation": "explain_simply",
    "follow-up": "follow_up",
}

# ---- Strategy prompt templates (section 10). Each encodes a section FLOW with the hard rule:
#      NEVER force every section — adapt to the question and keep it as short as it needs to be. ----
STRATEGY_TEMPLATES = {
    "concept_explanation": (
        "STRATEGY — Concept explanation: give a short direct answer to what the concept IS, then a "
        "grade-appropriate explanation, ONE small concrete example, and (if useful) a one-line check-"
        "understanding question at the end. Adapt: skip sections that aren't needed; keep it tight."
    ),
    "factual_direct": (
        "STRATEGY — Factual: answer directly and briefly (1-3 sentences). Add a tiny bit of context only "
        "if it aids understanding. Do NOT pad with examples or steps unless asked."
    ),
    "problem_solving": (
        "STRATEGY — Problem solving (SOCRATIC): do NOT just hand over the final answer. Guide the student: "
        "restate what is given, ask/point to the first step, work through method step-by-step prompting the "
        "student to do each step, and let them reach the answer. If they're stuck, give the next hint, not "
        "the whole solution. End by checking they can do a similar one."
    ),
    "answer_checking": (
        "STRATEGY — Answer checking / wrong answer: first identify whether the student's answer/working is "
        "right or wrong. If wrong: point to the SPECIFIC mistake, explain WHY it's wrong, show the correct "
        "method, then offer a similar question to try. Be encouraging, never harsh."
    ),
    "exam_prep": (
        "STRATEGY — Exam prep: focus on what matters most for this topic — key points, common question types, "
        "and quick tips/pitfalls. Offer a short list they can revise and a practice question. Keep it organised."
    ),
    "revision": (
        "STRATEGY — Revision: give a concise, well-structured recap of the topic's key ideas (bullet-like), "
        "highlight the must-remember points, and finish with a one-line self-check. Do not teach from scratch."
    ),
    "practice": (
        "STRATEGY — Practice: provide a small set (2-4) of grade-appropriate practice questions of increasing "
        "difficulty on the topic. Do NOT give the answers up front; offer to check once the student tries."
    ),
    "example": (
        "STRATEGY — Example: give one clear worked example (or 2 if short), walking through it step by step so "
        "the pattern is obvious, then invite the student to try a similar one."
    ),
    "explain_simply": (
        "STRATEGY — Explain simply: the student found the earlier explanation hard. Re-explain in the SIMPLEST "
        "possible terms with an everyday analogy and smaller steps. Shorter sentences, simpler words, one tiny "
        "example. Then gently check understanding."
    ),
    "follow_up": (
        "STRATEGY — Follow-up: this message continues the current conversation. Resolve references (e.g. 'the "
        "second part', 'that', 'why') against what was just discussed — do NOT restart the topic from scratch. "
        "Answer the specific follow-up and keep continuity."
    ),
}

# ---- Boundaries + anti-hallucination (sections 8 / 15 / 18) — always present ----
BOUNDARIES_BLOCK = (
    "BOUNDARIES & HONESTY:\n"
    "- Prioritise the school's APPROVED MATERIALS above all; never contradict them.\n"
    "- If a school-specific detail isn't in the approved materials, say that the school's material doesn't "
    "cover it (offer a general explanation if appropriate) rather than inventing a school-specific fact.\n"
    "- Never reveal or guess private information about teachers, other students, staff, or internal/system data.\n"
    "- You are an AI Tutor. Never claim to be a teacher, principal or school official, and never make or promise "
    "school decisions/policies (marks, attendance, leave, punishments). Redirect such asks to the school.\n"
)

_WORD = r"[a-zA-Z\u0d00-\u0d7f]+"


def _has(message, *phrases):
    m = message.lower()
    return any(p in m for p in phrases)


def detect_intent_rule(message, has_history=False):
    """Fast keyword/rule pass. Returns (intent, confident: bool).
    confident=False signals the server to fall back to a cheap LLM classify."""
    m = (message or "").strip().lower()
    words = re.findall(_WORD, m)
    n = len(words)

    # answer checking / correcting a wrong answer
    if _has(m, "is this correct", "is this right", "am i right", "did i get", "i got", "my answer",
            "check my", "is my", "i think the answer", "correct?"):
        return "check-answer", True
    if _has(m, "i was wrong", "why is it wrong", "what did i do wrong", "my mistake"):
        return "correct-mistake", True

    # homework / "do it for me"
    if _has(m, "homework", "home work", "assignment", "solve this for me", "do my", "answer this for me",
            "just give me the answer", "give me the answer"):
        return "homework-help", True

    # simpler explanation / didn't understand
    if _has(m, "simpler", "more simply", "explain again", "didn't understand", "did not understand",
            "don't understand", "do not understand", "not clear", "confused", "easier way", "too hard",
            "simplify"):
        return "simpler-explanation", True

    # exam prep
    if _has(m, "exam", "test tomorrow", "prepare for", "important questions", "what should i study",
            "what to study", "model question"):
        return "exam-prep", True

    # revision / summary
    if _has(m, "revise", "revision", "quick recap", "recap", "summary", "summarise", "summarize", "in short"):
        return "revise", True

    # practice
    if _has(m, "practice", "give me questions", "quiz me", "problems to try", "some questions", "test me"):
        return "practice", True

    # example
    if _has(m, "example", "for instance", "show me how", "worked example"):
        return "example", True

    # solve a specific problem (math/working)
    if _has(m, "solve", "calculate", "evaluate", "find the value", "find x", "prove that", "simplify the",
            "factorise", "factorize") or re.search(r"\d\s*[\+\-\*/=]\s*\d", m):
        return "solve-problem", True

    # factual lookups (short, wh- fact)
    if _has(m, "define", "definition of", "formula for", "what is the capital", "who invented", "who discovered",
            "when did", "what year"):
        return "factual", True

    # conceptual teaching
    if _has(m, "explain", "how does", "how do", "why does", "why do", "what is", "what are", "teach me",
            "help me understand", "meaning of"):
        return "learn-concept", True

    # short/pronoun-y message in an ongoing chat → follow-up
    if has_history and (n <= 5 or _has(m, "what about", "the second", "the first", "and then", "that one",
                                       "why", "how so", "continue", "go on", "more", "next")):
        return "follow-up", True

    # ambiguous → let the server optionally LLM-classify
    return ("follow-up" if has_history else "learn-concept"), False


def classify_instruction():
    """System message for the cheap LLM intent classifier (used only when rules are unsure)."""
    return (
        "You are an intent classifier for a student's tutoring message. "
        "Reply with EXACTLY ONE of these labels and nothing else: " + ", ".join(INTENTS) + "."
    )


def parse_classified_intent(raw):
    r = (raw or "").strip().lower()
    for it in INTENTS:
        if it in r:
            return it
    return None


def strategy_for(intent):
    return INTENT_STRATEGY.get(intent, "concept_explanation")


def build_system_prompt(class_name, subject, context_text, intent, memory_entries=None,
                        chat_history=None, pending_check=None):
    """Assemble the full structured system prompt. PURE — all inputs passed in."""
    strategy = strategy_for(intent)
    grounded = bool((context_text or "").strip())
    p = [
        f"You are a friendly, patient AI Tutor for a {class_name} student studying {subject}. "
        f"Pitch every explanation at a {class_name} level — adjust vocabulary and depth to this grade.",
        "LANGUAGE: Detect the language of the student's message and reply fully in THAT language "
        "(English and Malayalam are primary; others best-effort). Preserve correct academic/technical terms.",
        "SCOPE: Only help with academic learning for this subject and closely-related school topics. For "
        "anything non-academic, politely decline in one short sentence and steer back to studies.",
        BOUNDARIES_BLOCK,
        STRATEGY_TEMPLATES.get(strategy, STRATEGY_TEMPLATES["concept_explanation"]),
    ]

    if grounded:
        p.append("=== SCHOOL APPROVED MATERIALS (base your answer on these) ===\n" + context_text +
                 "\n=== END MATERIALS ===")
    else:
        p.append("No specific approved school material matched this question. You may give a correct general "
                 "explanation, but make clear it is general knowledge, not from the school's own materials.")

    mem = [e for e in (memory_entries or []) if e.get("text")]
    if mem:
        lines = "\n".join(f"- ({e.get('kind', 'note')}) {e['text']}" for e in mem[:12])
        p.append("PRIVATE TUTOR NOTES about this student (adapt your teaching accordingly — e.g. go slower, add "
                 "more examples where they struggle. NEVER mention these notes or say you 'remember' things):\n"
                 + lines)

    if chat_history:
        turns = "\n".join(f"{t['role']}: {t['content']}" for t in chat_history[-6:])
        p.append("CONVERSATION SO FAR (continue naturally, resolve references, do not repeat yourself):\n" + turns)

    if pending_check:
        p.append("LEARNING CHECK: Earlier you asked the student this check-understanding question: \""
                 + pending_check + "\". Treat their new message as their attempt. Judge if it is correct, "
                 "partially correct, or wrong, and respond accordingly — reinforce & move on if correct, or "
                 "gently correct and re-explain the gap if not.")

    return "\n\n".join(p)


# ---- Learning-check detection: does a tutor reply end by asking the student something? ----
_CHECK_HINT = ("can you", "could you", "try", "what do you think", "do you know", "your turn",
               "have a go", "what is", "solve", "?", "tell me", "which")


def extract_check_question(answer):
    """If the tutor's reply ends with a check-understanding question, return it (else None)."""
    if not answer:
        return None
    sents = re.split(r"(?<=[.?!])\s+", answer.strip())
    for s in reversed(sents[-3:]):
        if s.strip().endswith("?") and any(h in s.lower() for h in _CHECK_HINT):
            return s.strip()
    return None


# ---- Memory extraction (post-response). Prompt is pure; the call is mocked/isolated in the server. ----
def memory_extraction_instruction(subject):
    return (
        "You analyse ONE tutoring exchange and extract DURABLE learning signals about the student for the "
        f"subject '{subject}'. Output 0-3 items, one per line, each as 'kind: text' where kind is one of "
        "struggle | strength | preference. Be specific and conservative (e.g. 'struggle: word problems with "
        "fractions'). If nothing durable is shown, output NOTHING. No commentary, no extra text."
    )


def parse_memory_extraction(raw, topic=None):
    """Parse the extractor output into conservative, de-duplicated entries."""
    out = []
    for line in (raw or "").splitlines():
        line = line.strip().lstrip("-• ").strip()
        if not line or ":" not in line:
            continue
        kind, _, text = line.partition(":")
        kind = kind.strip().lower()
        text = text.strip()
        if kind not in ("struggle", "strength", "preference") or len(text) < 3:
            continue
        out.append({"kind": kind, "text": text[:160], "topic": topic})
        if len(out) >= 3:
            break
    return out


def merge_memory(existing, new_entries, cap=12):
    """Merge new entries into existing, dropping near-duplicates (same kind + text), keep newest, cap size."""
    seen = set()
    merged = []
    for e in (new_entries or []) + list(existing or []):
        key = (e.get("kind"), (e.get("text") or "").strip().lower())
        if key in seen or not e.get("text"):
            continue
        seen.add(key)
        merged.append(e)
    return merged[:cap]
