import { defineConfig } from 'vitepress'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { withMermaid } from 'vitepress-plugin-mermaid'

const here = path.dirname(fileURLToPath(import.meta.url))

function titleOf(file: string, slug: string): string {
  try {
    const m = fs.readFileSync(file, 'utf8').match(/^---\n([\s\S]*?)\n---/)
    if (m) { const t = m[1].match(/^title:\s*(.*)$/m); if (t) return t[1].trim().replace(/^["']|["']$/g, '') }
  } catch {}
  return slug
}
function sidebarFor(subdir: string, label: string, base: string) {
  const dir = path.resolve(here, '..', subdir)
  if (!fs.existsSync(dir)) return []
  const items = fs.readdirSync(dir).filter(f => f.endsWith('.md') && f !== 'index.md').sort().reverse()
    .map(f => ({ text: titleOf(path.join(dir, f), f.replace(/\.md$/, '')), link: `${base}${f.replace(/\.md$/, '')}` }))
  return [{ text: label, items }]
}

export default withMermaid(defineConfig({
  title: 'note vault',
  description: 'Parsed notes — searchable.',
  cleanUrls: true, lastUpdated: true, appearance: 'dark',
  themeConfig: {
    search: { provider: 'local' },
    nav: [
      { text: 'Notes', link: '/notes/' },
      { text: 'Daily', link: '/notes/daily/' },
      { text: 'Tags', link: '/tags' },
      { text: 'Timeline', link: '/timeline' },
      { text: 'Graph', link: '/graph' },
    ],
    sidebar: {
      '/notes/daily/': sidebarFor('notes/daily', 'Daily', '/notes/daily/'),
      '/notes/': sidebarFor('notes', 'Notes', '/notes/'),
    },
    outline: 'deep', docFooter: { prev: false, next: false },
  },
}))
