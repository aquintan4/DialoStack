/**
 * Strategy metadata for the Strategies page: what each dialogue strategy does,
 * which canned phrases belong to it, and which Frame Builder kind builds its
 * payload. The phrase keys mirror the engine's per-language set
 * (ros2_dialog_manager/llm_client.py _LANG_FALLBACKS) plus the slot-filling
 * `ack` list. Anything not listed here still shows under "Other".
 */

// Human labels + an optional hint per phrase key (the raw text is what the
// robot says when the LLM is unavailable, in the active dialogue language).
export const PHRASE_LABELS = {
  opening: 'Opening / greeting',
  resume: 'Resume (continuing a task)',
  unclear: "Didn't understand",
  timeout: 'Timeout (user went quiet)',
  good_question: 'Acknowledge a user question',
  intent_response: 'Generic intent reply',
  cancel_ask: 'Cancel — confirm',
  cancel_ok: 'Cancel — confirmed',
  cancel_no: 'Cancel — dismissed',
  confirm_q: 'Confirm collected data',
  explain_open: 'Explanation opening',
  understand_check: 'Check understanding',
  understand_ok: 'Understood — proceed',
  understand_fail: 'Gave up explaining',
  quiz_opening: 'Quiz opening',
  quiz_summary: 'Quiz summary',
  quiz_correct: 'Correct answer',
  quiz_wrong: 'Wrong answer ({expected})',
}

// The slot-filling acknowledgments are a LIST (a random one is spoken after a
// slot is filled), edited as one-per-line, stored as an array.
export const ACK_KEY = 'ack'

export const STRATEGIES = [
  {
    id: 'shared',
    label: 'Shared',
    frameKind: null,
    summary: 'Lines any strategy can use.',
    desc: 'Greeting, resume, "I didn’t catch that", the timeout nudge and the whole cancel flow. These apply to every strategy.',
    keys: [
      'opening', 'resume', 'unclear', 'timeout', 'good_question',
      'intent_response', 'cancel_ask', 'cancel_ok', 'cancel_no',
    ],
  },
  {
    id: 'slot_filling',
    label: 'Slot filling',
    frameKind: 'slot_filling',
    summary: 'Collects structured data slot by slot, then confirms.',
    desc: 'Asks for each slot the task needs, extracts values from free speech and confirms the result. Define its slots (and optional context resources) in the Frame Builder.',
    keys: ['confirm_q'],
    ack: true,
  },
  {
    id: 'explanation',
    label: 'Explanation',
    frameKind: 'explanation',
    summary: 'Explains reference material and checks understanding.',
    desc: 'Presents material to the user and verifies they understood, rephrasing on demand. Provide the material as resources in the Frame Builder.',
    keys: ['explain_open', 'understand_check', 'understand_ok', 'understand_fail'],
  },
  {
    id: 'quiz',
    label: 'Quiz',
    frameKind: 'quiz',
    summary: 'Asks a question bank and scores the answers.',
    desc: 'Runs through a bank of questions, judges each answer and summarises the score. Build the question bank in the Frame Builder.',
    keys: ['quiz_opening', 'quiz_summary', 'quiz_correct', 'quiz_wrong'],
  },
]

export const phraseLabel = (key) => PHRASE_LABELS[key] || key
