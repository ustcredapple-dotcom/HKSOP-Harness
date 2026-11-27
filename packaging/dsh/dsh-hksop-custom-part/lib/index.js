import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = "dsh-hksop-custom-part"
export const inject = ['skills']

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const skillNames = ["custom-part-cad", "library-intake"]

function loadSkill(skillName, rules) {
  const directory = join(root, 'skills', skillName)
  const path = join(directory, 'SKILL.md')
  const text = readFileSync(path, 'utf8').replace(/\r\n/g, '\n')
  const header = /^---\n([\s\S]*?)\n---\n([\s\S]+)$/.exec(text)
  const fields = header?.[1].split('\n') ?? []
  const description = fields.find(line => line.startsWith('description: '))?.slice(13).trim()
  if (!description || !fields.includes('name: ' + skillName)) {
    throw new Error('Invalid bundled HKSOP skill metadata in ' + path)
  }
  return {
    name: skillName, description, source: 'runtime', provider: name, path,
    resourceBase: { kind: 'directory', path: directory },
    invocation: { modelInvocable: true, userInvocable: true },
    content: header[2].trim() + '\n\n' + rules + '\n',
  }
}

export function apply(ctx) {
  const rules = readFileSync(join(root, 'rules', 'AGENTS.md'), 'utf8').trim()
  const definitions = skillNames.map(skillName => loadSkill(skillName, rules))
  for (const definition of definitions) ctx.skills.register(definition)
}
