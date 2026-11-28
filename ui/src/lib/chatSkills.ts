/**
 * Skills invoked from the chat composer. A message that starts with
 * `/skill:<name>` runs that skill: the agent runtime replaces the command with
 * the skill's instructions and keeps the rest of the message as its arguments.
 */

/** What a message starts with to invoke a skill, as pi spells it. */
const SKILL_COMMAND_PREFIX = "/skill:";

/** A skill the runtime has loaded, as the composer offers it. */
export interface ChatSkill {
  name: string;
  description?: string;
}

/**
 * The skill name being typed, or null when the text is not a skill command in
 * progress. The command is the whole text so far: a leading `/`, optionally
 * `skill:`, and no whitespace yet. Once a space or line break follows, the user
 * is writing arguments and the menu stays closed.
 */
export function skillQuery(value: string): string | null {
  const match = /^\/(?:skill:)?(\S*)$/.exec(value);
  return match ? match[1] : null;
}

/**
 * Skills that match the query, case-insensitively: names that start with it,
 * then names that contain it, then descriptions that contain it. An empty query
 * lists every skill in the order given.
 */
export function matchSkills(skills: readonly ChatSkill[], query: string): ChatSkill[] {
  const q = query.toLowerCase();
  if (!q) return [...skills];
  const prefix: ChatSkill[] = [];
  const inName: ChatSkill[] = [];
  const inDescription: ChatSkill[] = [];
  for (const skill of skills) {
    const name = skill.name.toLowerCase();
    if (name.startsWith(q)) prefix.push(skill);
    else if (name.includes(q)) inName.push(skill);
    else if (skill.description?.toLowerCase().includes(q)) inDescription.push(skill);
  }
  return [...prefix, ...inName, ...inDescription];
}

/** The text that invokes a skill, with a trailing space for its arguments. */
export function skillInvocation(name: string): string {
  return `${SKILL_COMMAND_PREFIX}${name} `;
}
