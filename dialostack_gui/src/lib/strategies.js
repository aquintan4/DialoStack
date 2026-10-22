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
  procedure_opening: 'Procedure opening',
  procedure_step: 'Present a step ({n}, {total}, {step})',
  procedure_remind: 'Remind to report the step',
  procedure_summary: 'Procedure summary',
  roleplay_intro: 'Roleplay introduction',
  roleplay_reply: 'Character line (LLM down)',
  roleplay_coach: 'Hint for the user',
  roleplay_feedback: 'Closing feedback',
  roleplay_scores: 'Scores sentence ({scores})',
  roleplay_score_item: 'One score ({criterion}, {score})',
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
  {
    id: 'procedure',
    label: 'Procedure',
    frameKind: 'procedure',
    summary: 'Guides the user through ordered steps, one at a time.',
    desc: 'Presents each step, waits until the user reports it done, answers questions, helps when they are stuck and lets them repeat, go back or skip. Define the steps in the Frame Builder.',
    keys: ['procedure_opening', 'procedure_step', 'procedure_remind', 'procedure_summary'],
  },
  {
    id: 'roleplay',
    label: 'Roleplay',
    frameKind: 'roleplay',
    summary: 'Acts out a scene so the user can practise, then scores them.',
    desc: 'The robot plays a character (an interviewer, a waiter, a patient...) while the user practises. They can ask for a hint at any moment; at the end the robot steps out of the role and scores each criterion of the rubric. Define the scene in the Frame Builder.',
    keys: ['roleplay_intro', 'roleplay_reply', 'roleplay_coach', 'roleplay_feedback', 'roleplay_scores', 'roleplay_score_item'],
  },
]

export const phraseLabel = (key) => PHRASE_LABELS[key] || key
