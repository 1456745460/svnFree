import type { SvnStatusItem } from "../types";

/** 树形指示线：pass 贯穿，empty 只占位，elbow* 是当前节点的拐角。 */
export type ChangeTreeGuide = "pass" | "empty" | "elbow" | "elbow-first" | "elbow-last" | "none";

export type ChangeTreeNode = {
  /** 相对路径，用 / 连接；路径段本身可以含反斜杠（macOS/Linux 文件名） */
  key: string;
  name: string;
  isDir: boolean;
  item?: SvnStatusItem;
  children: ChangeTreeNode[];
  /** 自身加上全部后代里真正有 SVN 状态的项，用于文件夹勾选 */
  items: SvnStatusItem[];
};

export type FlatChangeRow = {
  node: ChangeTreeNode;
  depth: number;
  guides: ChangeTreeGuide[];
};

/**
 * Windows 盘符路径才把 `\` 当分隔符。
 * macOS/Linux 上 `\` 是合法文件名字符，例如目录名 `D:\maven` 不能拆成 `D:/`。
 */
export function usesWindowsSeparators(root: string | undefined, items: { path?: string }[]): boolean {
  const raw = (root || items.find((item) => item.path)?.path || "").trim();
  return /^[A-Za-z]:[\\/]/.test(raw) || raw.startsWith("\\\\");
}

export function splitChangePath(rel: string, windows: boolean): string[] {
  if (!rel) return [];
  const text = windows ? rel.replace(/\\/g, "/") : rel;
  return text.split("/").filter((part) => part.length > 0);
}

function elbowKind(isFirst: boolean, isLast: boolean, depth: number): ChangeTreeGuide {
  if (isFirst && isLast && depth === 0) return "none";
  // 根上的第一项不要往上伸出竖线；嵌套的第一项仍从行顶连下来，避免和父节点断开。
  if (isFirst && !isLast && depth === 0) return "elbow-first";
  if (isLast) return "elbow-last";
  return "elbow";
}

export function buildChangeTree(items: SvnStatusItem[], root?: string): ChangeTreeNode[] {
  const windows = usesWindowsSeparators(root, items);
  const top: ChangeTreeNode = { key: "", name: "", isDir: true, children: [], items: [] };
  const index = new Map<string, ChangeTreeNode>([["", top]]);

  for (const item of items) {
    const rel = (item.relativePath || item.name || "").trim();
    let parts = splitChangePath(rel, windows);
    if (!parts.length && item.name) parts = [item.name];
    if (!parts.length) continue;

    let parentKey = "";
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      const key = parentKey ? `${parentKey}/${name}` : name;
      const isLast = i === parts.length - 1;
      let node = index.get(key);
      if (!node) {
        node = {
          key,
          name,
          isDir: isLast ? Boolean(item.isDir) : true,
          item: isLast ? item : undefined,
          children: [],
          items: [],
        };
        index.set(key, node);
        index.get(parentKey)!.children.push(node);
      } else if (isLast) {
        node.item = item;
        if (item.isDir) node.isDir = true;
      }
      if (!isLast) node.isDir = true;
      parentKey = key;
    }
  }

  const sortNodes = (nodes: ChangeTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
    });
    for (const node of nodes) sortNodes(node.children);
  };
  sortNodes(top.children);

  const collect = (node: ChangeTreeNode): SvnStatusItem[] => {
    const list: SvnStatusItem[] = [];
    if (node.item) list.push(node.item);
    for (const child of node.children) list.push(...collect(child));
    node.items = list;
    return list;
  };
  collect(top);
  return top.children.map(compactChangeNode);
}

/**
 * 和 VS Code 源代码管理树一样：连续只有一个子目录的层级收成 `src/main` 这种路径。
 * 文件不并进目录名，分叉目录（下面有多个子项）就停住。
 */
function compactChangeNode(node: ChangeTreeNode): ChangeTreeNode {
  if (!node.isDir) return node;

  const chain: ChangeTreeNode[] = [node];
  let cursor = node;
  while (cursor.children.length === 1 && cursor.children[0].isDir) {
    cursor = cursor.children[0];
    chain.push(cursor);
  }

  const leaf = chain[chain.length - 1];
  return {
    key: leaf.key,
    name: chain.map((part) => part.name).join("/"),
    isDir: true,
    item: [...chain].reverse().find((part) => part.item)?.item,
    children: leaf.children.map(compactChangeNode),
    items: node.items,
  };
}

export function flattenChangeTree(
  nodes: ChangeTreeNode[],
  collapsed: Record<string, boolean>,
  ancestors: boolean[] = [],
): FlatChangeRow[] {
  const rows: FlatChangeRow[] = [];
  nodes.forEach((node, index) => {
    const isFirst = index === 0;
    const isLast = index === nodes.length - 1;
    const depth = ancestors.length;
    rows.push({
      node,
      depth,
      guides: [
        ...ancestors.map((continues) => (continues ? "pass" : "empty") as ChangeTreeGuide),
        elbowKind(isFirst, isLast, depth),
      ],
    });
    if (node.children.length && !collapsed[node.key]) {
      rows.push(...flattenChangeTree(node.children, collapsed, [...ancestors, !isLast]));
    }
  });
  return rows;
}

export function branchKeys(nodes: ChangeTreeNode[]): string[] {
  const keys: string[] = [];
  const walk = (list: ChangeTreeNode[]) => {
    for (const node of list) {
      if (node.children.length) {
        keys.push(node.key);
        walk(node.children);
      }
    }
  };
  walk(nodes);
  return keys;
}
