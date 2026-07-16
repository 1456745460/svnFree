import { diffLines } from "diff";

export type LineType = "add" | "del" | "ctx" | "mod" | "empty";

export interface UnifiedRow {
  type: "add" | "del" | "ctx";
  oldLine: number | null;
  newLine: number | null;
  text: string;
}

export interface SideCell {
  line: number | null;
  text: string;
  type: LineType;
}

export interface SideBySideRow {
  type: "add" | "del" | "ctx" | "mod";
  left: SideCell;
  right: SideCell;
}

export interface BuiltDiff {
  unified: UnifiedRow[];
  sideBySide: SideBySideRow[];
  stats: { additions: number; deletions: number };
}

export type RenderBlock =
  | { kind: "row"; row: any; index: number }
  | { kind: "hunk"; hidden: number; from: number; to: number };

function pairSideBySide(rows: SideBySideRow[]): SideBySideRow[] {
  const result: SideBySideRow[] = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (row.type === "del") {
      const dels: SideBySideRow[] = [];
      const adds: SideBySideRow[] = [];
      while (i < rows.length && rows[i].type === "del") {
        dels.push(rows[i]);
        i += 1;
      }
      while (i < rows.length && rows[i].type === "add") {
        adds.push(rows[i]);
        i += 1;
      }
      const max = Math.max(dels.length, adds.length);
      for (let k = 0; k < max; k += 1) {
        const left = dels[k]
          ? dels[k].left
          : { line: null, text: "", type: "empty" as const };
        const right = adds[k]
          ? adds[k].right
          : { line: null, text: "", type: "empty" as const };
        let type: SideBySideRow["type"] = "ctx";
        if (dels[k] && adds[k]) type = "mod";
        else if (dels[k]) type = "del";
        else type = "add";
        result.push({ type, left, right });
      }
    } else {
      result.push(row);
      i += 1;
    }
  }
  return result;
}

export function buildLineDiff(oldText: string, newText: string): BuiltDiff {
  const parts = diffLines(oldText, newText);
  const unified: UnifiedRow[] = [];
  const sideBySide: SideBySideRow[] = [];
  let oldLine = 1;
  let newLine = 1;

  for (const part of parts) {
    const rawLines = part.value.split("\n");
    if (rawLines.length && rawLines[rawLines.length - 1] === "") rawLines.pop();

    if (part.added) {
      for (const text of rawLines) {
        unified.push({ type: "add", oldLine: null, newLine, text });
        sideBySide.push({
          type: "add",
          left: { line: null, text: "", type: "empty" },
          right: { line: newLine, text, type: "add" },
        });
        newLine += 1;
      }
    } else if (part.removed) {
      for (const text of rawLines) {
        unified.push({ type: "del", oldLine, newLine: null, text });
        sideBySide.push({
          type: "del",
          left: { line: oldLine, text, type: "del" },
          right: { line: null, text: "", type: "empty" },
        });
        oldLine += 1;
      }
    } else {
      for (const text of rawLines) {
        unified.push({ type: "ctx", oldLine, newLine, text });
        sideBySide.push({
          type: "ctx",
          left: { line: oldLine, text, type: "ctx" },
          right: { line: newLine, text, type: "ctx" },
        });
        oldLine += 1;
        newLine += 1;
      }
    }
  }

  return {
    unified,
    sideBySide: pairSideBySide(sideBySide),
    stats: {
      additions: unified.filter((r) => r.type === "add").length,
      deletions: unified.filter((r) => r.type === "del").length,
    },
  };
}

export function isChangeType(type: string | undefined | null) {
  return type === "add" || type === "del" || type === "mod";
}

export function collapseRows<T>(
  rows: T[],
  getType: (row: T) => string,
  enabled: boolean,
  context = 3,
): Array<{ kind: "row"; row: T } | { kind: "hunk"; hidden: number; from: number; to: number }> {
  if (!enabled) {
    return rows.map((row) => ({ kind: "row" as const, row }));
  }

  const keep = new Array(rows.length).fill(false);
  for (let i = 0; i < rows.length; i += 1) {
    if (isChangeType(getType(rows[i]))) {
      for (let j = Math.max(0, i - context); j <= Math.min(rows.length - 1, i + context); j += 1) {
        keep[j] = true;
      }
    }
  }

  const out: Array<{ kind: "row"; row: T } | { kind: "hunk"; hidden: number; from: number; to: number }> = [];
  let i = 0;
  while (i < rows.length) {
    if (keep[i]) {
      out.push({ kind: "row", row: rows[i] });
      i += 1;
    } else {
      const start = i;
      while (i < rows.length && !keep[i]) i += 1;
      out.push({ kind: "hunk", hidden: i - start, from: start, to: i });
    }
  }
  return out;
}

export function assignDiffBlockIds(
  rows: Array<{ type: string }>,
  getType: (row: { type: string }) => string,
): Array<number | null> {
  const ids: Array<number | null> = new Array(rows.length).fill(null);
  let blockId = 0;
  let i = 0;
  while (i < rows.length) {
    if (!isChangeType(getType(rows[i]))) {
      i += 1;
      continue;
    }
    const id = blockId++;
    while (i < rows.length && isChangeType(getType(rows[i]))) {
      ids[i] = id;
      i += 1;
    }
  }
  return ids;
}

export function blockEdgeClass(blockIds: Array<number | null>, index: number) {
  const id = blockIds[index];
  if (id == null) return "";
  const prev = index > 0 ? blockIds[index - 1] : null;
  const next = index < blockIds.length - 1 ? blockIds[index + 1] : null;
  const start = prev !== id;
  const end = next !== id;
  if (start && end) return " block-single";
  if (start) return " block-start";
  if (end) return " block-end";
  return " block-mid";
}

export function blockTypeClass(type: string) {
  if (type === "add") return " block-type-add";
  if (type === "del") return " block-type-del";
  if (type === "mod") return " block-type-mod";
  return "";
}

export function splitName(path: string) {
  const normalized = path.replace(/\\/g, "/");
  const idx = normalized.lastIndexOf("/");
  if (idx < 0) return { dir: "", name: normalized };
  return { dir: normalized.slice(0, idx + 1), name: normalized.slice(idx + 1) };
}

export function statusIcon(status: string) {
  const s = (status || "").toLowerCase();
  if (s === "added" || s === "unversioned" || status === "A" || status === "?") return "A";
  if (s === "deleted" || status === "D" || status === "!") return "D";
  return "M";
}

export function statusClass(status: string) {
  const s = (status || "").toLowerCase();
  if (s === "added" || s === "unversioned" || status === "A" || status === "?") return "added";
  if (s === "deleted" || status === "D" || status === "!") return "deleted";
  return "modified";
}

export function statusLabel(status: string, statusLabelText?: string) {
  if (statusLabelText) {
    const map: Record<string, string> = {
      added: "新增",
      deleted: "删除",
      modified: "修改",
      unversioned: "未版本控制",
      replaced: "替换",
      conflicted: "冲突",
    };
    return map[statusLabelText] || statusLabelText;
  }
  const s = (status || "").toUpperCase();
  if (s === "A") return "新增";
  if (s === "D" || s === "!") return "删除";
  if (s === "?") return "未版本控制";
  if (s === "C") return "冲突";
  if (s === "R") return "替换";
  return "修改";
}

export function escapeHtml(text: string) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function resolveHighlightLang(language: string) {
  const lang = (language || "").toLowerCase();
  if (!lang || lang === "plaintext" || lang === "text") return null;
  return lang;
}
