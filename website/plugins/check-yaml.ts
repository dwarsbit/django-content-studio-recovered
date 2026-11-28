// Fails the build when a ```yaml block in the docs does not parse: a syntax
// error, a duplicate key or an alias without its anchor. Readers copy these
// blocks as files (such as compose.yaml), so a broken one must not ship.
import fs from "node:fs/promises";
import path from "node:path";
import type { LoadContext, Plugin } from "@docusaurus/types";
import { parseAllDocuments } from "yaml";

const YAML_FENCE = /^(\s*)(```|~~~)ya?ml\b.*$/;

type Block = { start: number; source: string };

// The yaml blocks of one page, with the line their first line is on.
export function yamlBlocks(markdown: string): Block[] {
  const lines = markdown.split("\n");
  const blocks: Block[] = [];

  for (let i = 0; i < lines.length; i++) {
    const open = lines[i].match(YAML_FENCE);

    if (!open) {
      continue;
    }

    const [, indent, fence] = open;
    const body: string[] = [];
    let j = i + 1;

    while (j < lines.length && lines[j].trim() !== fence) {
      // Blocks inside list items are indented with the item.
      body.push(lines[j].startsWith(indent) ? lines[j].slice(indent.length) : lines[j]);
      j++;
    }

    blocks.push({ start: i + 2, source: body.join("\n") });
    i = j;
  }

  return blocks;
}

// One message per problem, as "<file>:<line>: <message>".
export function checkYaml(file: string, markdown: string): string[] {
  const problems: string[] = [];

  for (const block of yamlBlocks(markdown)) {
    for (const doc of parseAllDocuments(block.source, { merge: true })) {
      const errors = [...doc.errors, ...doc.warnings];

      for (const error of errors) {
        const line = block.start + (error.linePos?.[0].line ?? 1) - 1;
        const message = error.message.split("\n")[0].replace(/ at line \d+, column \d+:?$/, "");
        problems.push(`${file}:${line}: ${message}`);
      }

      // An alias without its anchor only fails when the values are read.
      if (!errors.length) {
        try {
          doc.toJS();
        } catch (error) {
          problems.push(`${file}:${block.start}: ${(error as Error).message}`);
        }
      }
    }
  }

  return problems;
}

export default function checkYamlPlugin(context: LoadContext): Plugin {
  const docsDir = path.join(context.siteDir, "docs");

  return {
    name: "check-yaml",

    async loadContent() {
      const files = (await fs.readdir(docsDir)).filter((name) => /\.mdx?$/.test(name)).sort();
      const problems: string[] = [];

      for (const name of files) {
        const markdown = await fs.readFile(path.join(docsDir, name), "utf8");
        problems.push(...checkYaml(path.join("docs", name), markdown));
      }

      if (problems.length) {
        throw new Error(`Invalid YAML in the docs:\n${problems.join("\n")}`);
      }
    },
  };
}
