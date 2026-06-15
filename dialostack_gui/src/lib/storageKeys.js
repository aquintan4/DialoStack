/**
 * All of the GUI localStorage keys, in a single place.
 *
 * Centralizing them avoids the footgun of loose strings (a misspelled key =
 * silent data loss) and documents at a glance what the app persists. The
 * frames/handoff keys are re-exported from lib/frames.js with their historical
 * names (LIBRARY_KEY, ...) so their importers don't break.
 */
export const STORAGE = {
  config: 'dialostack_gui_config',
  monitorTags: 'dialostack_monitor_tags',

  // Launcher (task draft + saved tasks)
  launchForm: 'dialostack_launch_form',
  launchSchema: 'dialostack_launch_schema',
  launchResources: 'dialostack_launch_resources',
  launchQuiz: 'dialostack_launch_quiz',
  launchSchemaOpen: 'dialostack_launch_schema_open',
  launchResourcesOpen: 'dialostack_launch_resources_open',
  taskPresets: 'dialostack_task_presets',

  // Frame Builder (per-mode draft + frame library)
  builderKind: 'dialostack_builder_kind',
  builderSlots: 'dialostack_builder_slots',
  builderQuiz: 'dialostack_builder_quiz',
  builderResources: 'dialostack_builder_resources',
  frames: 'dialostack_frames',

  // Prompts (override profiles)
  promptProfiles: 'dialostack_prompt_profiles',

  // Handoff channels between views (not drafts: read once and then cleared)
  handoffToBuilder: 'dialostack_builder_handoff',
  injectToLaunch: 'dialostack_launch_inject',
}
