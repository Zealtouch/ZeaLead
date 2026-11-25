"use client";
"use no memo";

import * as React from "react";

import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge as RFEdge,
  Handle,
  MarkerType,
  MiniMap,
  type Node as RFNode,
  type NodeProps,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Compass, FlaskConical, type LucideIcon, Target, UserCheck } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { t } from "@/i18n";
import { platformLabel } from "@/lib/status";
import type { GraphEdge, GraphNode, NodeKind } from "@/lib/types";
import { cn } from "@/lib/utils";

export const relLabel: Record<string, string> = {
  spawns: t("spawns"),
  derived_from: t("intent chain"),
  yields: t("yields"),
  proves: t("proves"),
};

export const relColor: Record<string, string> = {
  spawns: "#10b981",
  derived_from: "#6366f1",
  yields: "#f59e0b",
  proves: "#ef4444",
};

type TypeMeta = { label: string; icon: LucideIcon; iconBg: string; hex: string };

export const typeMeta: Record<Exclude<NodeKind, "hint">, TypeMeta> = {
  goal: { label: t("Goal"), icon: Target, iconBg: "bg-emerald-500", hex: "#10b981" },
  intent: { label: t("Intent"), icon: Compass, iconBg: "bg-blue-500", hex: "#3b82f6" },
  fact: { label: t("Fact"), icon: FlaskConical, iconBg: "bg-amber-500", hex: "#f59e0b" },
  lead: { label: t("Lead"), icon: UserCheck, iconBg: "bg-rose-500", hex: "#f43f5e" },
};

const COL_W = 330;
const ROW_H = 130;

function pushMap(m: Map<number, number[]>, k: number, v: number) {
  const a = m.get(k);
  if (a) a.push(v);
  else m.set(k, [v]);
}

// Layered layout (from ARTEX): longest-path layers along edges with cycle-safe back-edge
// removal, then barycenter sweeps to reduce crossings, so goal → intent → fact/lead reads
// left to right.
function computeLayout(nodes: GraphNode[], edges: GraphEdge[]): Map<number, { x: number; y: number }> {
  const order = nodes.map((n) => n.id);
  const idset = new Set(order);
  const valid = edges.filter((e) => idset.has(e.source) && idset.has(e.target));
  const key = (s: number, d: number) => `${s}->${d}`;
  const out = new Map<number, number[]>();
  for (const e of valid) pushMap(out, e.source, e.target);

  const seen = new Map<number, 0 | 1 | 2>();
  const back = new Set<string>();
  for (const root of order) {
    if ((seen.get(root) ?? 0) !== 0) continue;
    const stack: Array<{ u: number; i: number }> = [{ u: root, i: 0 }];
    seen.set(root, 1);
    while (stack.length) {
      const top = stack[stack.length - 1];
      const nbrs = out.get(top.u) ?? [];
      if (top.i >= nbrs.length) {
        seen.set(top.u, 2);
        stack.pop();
        continue;
      }
      const v = nbrs[top.i++];
      const s = seen.get(v) ?? 0;
      if (s === 1) back.add(key(top.u, v));
      else if (s === 0) {
        seen.set(v, 1);
        stack.push({ u: v, i: 0 });
      }
    }
  }

  const succ = new Map<number, number[]>();
  const indeg = new Map<number, number>(order.map((id) => [id, 0]));
  for (const e of valid) {
    if (back.has(key(e.source, e.target))) continue;
    pushMap(succ, e.source, e.target);
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1);
  }
  const layer = new Map<number, number>(order.map((id) => [id, 0]));
  const queue = order.filter((id) => (indeg.get(id) ?? 0) === 0);
  for (let qi = 0; qi < queue.length; qi++) {
    const u = queue[qi];
    for (const v of succ.get(u) ?? []) {
      layer.set(v, Math.max(layer.get(v) ?? 0, (layer.get(u) ?? 0) + 1));
      const d = (indeg.get(v) ?? 0) - 1;
      indeg.set(v, d);
      if (d === 0) queue.push(v);
    }
  }

  const maxLayer = Math.max(0, ...layer.values());
  const columns: number[][] = Array.from({ length: maxLayer + 1 }, () => []);
  for (const id of order) columns[layer.get(id) ?? 0].push(id);

  const colOf = new Map<number, number>();
  columns.forEach((ids, c) => ids.forEach((id) => colOf.set(id, c)));
  const neighbors = new Map<number, number[]>();
  for (const e of valid) {
    const cs = colOf.get(e.source);
    const cd = colOf.get(e.target);
    if (cs === undefined || cd === undefined || Math.abs(cs - cd) !== 1) continue;
    pushMap(neighbors, e.source, e.target);
    pushMap(neighbors, e.target, e.source);
  }
  const sweep = (dir: 1 | -1) => {
    const start = dir === 1 ? 1 : columns.length - 2;
    const end = dir === 1 ? columns.length : -1;
    for (let c = start; c !== end; c += dir) {
      const refIndex = new Map(columns[c - dir].map((id, i) => [id, i]));
      const scored = columns[c].map((id, i) => {
        const ns = (neighbors.get(id) ?? []).map((n) => refIndex.get(n)).filter((v): v is number => v !== undefined);
        return { id, i, bary: ns.length ? ns.reduce((a, b) => a + b, 0) / ns.length : i };
      });
      scored.sort((a, b) => a.bary - b.bary || a.i - b.i);
      columns[c] = scored.map((s) => s.id);
    }
  };
  for (let iter = 0; iter < 4; iter++) {
    sweep(1);
    sweep(-1);
  }

  const maxCount = Math.max(1, ...columns.map((c) => c.length));
  const midline = ((maxCount - 1) * ROW_H) / 2;
  const pos = new Map<number, { x: number; y: number }>();
  columns.forEach((ids, c) => {
    const startY = midline - ((ids.length - 1) * ROW_H) / 2;
    ids.forEach((id, i) => pos.set(id, { x: c * COL_W, y: startY + i * ROW_H }));
  });
  return pos;
}

type ExploreRFNode = RFNode<{ node: GraphNode }, "explore">;

function ExploreNode({ data, selected }: NodeProps<ExploreRFNode>) {
  const n = data.node;
  const meta = typeMeta[n.kind as keyof typeof typeMeta] ?? typeMeta.intent;
  const Icon = meta.icon;
  const isLive = n.kind === "intent" && n.state === "running";
  const domain = n.kind === "goal" ? "goal" : n.kind === "intent" ? "intent" : "node";
  return (
    <div
      className={cn(
        "w-[230px] cursor-pointer rounded-2xl border-2 transition-colors",
        selected ? "border-blue-500" : isLive ? "border-blue-400/70" : "border-transparent",
      )}
    >
      <div className="group relative rounded-[14px] border border-black/[0.06] bg-white shadow-sm transition-shadow hover:shadow-lg dark:border-white/10 dark:bg-neutral-900">
        <Handle type="target" position={Position.Left} className="!size-2 opacity-0" />
        <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
          <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-lg shadow-sm", meta.iconBg)}>
            <Icon className="size-3.5 text-white" />
          </span>
          <span className="grow truncate font-semibold text-[13px] text-neutral-700 dark:text-neutral-100">
            {meta.label}
            {n.platform && (
              <span className="ml-1.5 font-normal text-neutral-400 text-xs">{platformLabel(n.platform)}</span>
            )}
          </span>
          {isLive && (
            <span className="relative flex size-2 shrink-0">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue-400 opacity-70" />
              <span className="relative inline-flex size-2 rounded-full bg-blue-500" />
            </span>
          )}
        </div>
        <div className="line-clamp-3 px-3 pb-2 text-[13px] text-neutral-500 leading-snug dark:text-neutral-400">
          {n.summary || meta.label}
        </div>
        <div className="flex items-center justify-between gap-2 px-3 pb-2.5">
          <StatusBadge domain={domain} value={n.state} dot className="px-1.5 py-0 text-[10px]" />
          <span className="shrink-0 font-mono text-[10px] text-neutral-400 dark:text-neutral-500">#{n.id}</span>
        </div>
        <Handle type="source" position={Position.Right} className="!size-2 opacity-0" />
      </div>
    </div>
  );
}

const nodeTypes = { explore: ExploreNode };

function GraphInner({
  nodes,
  edges,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const rf = React.useMemo(() => {
    const pos = computeLayout(nodes, edges);
    const rfNodes: ExploreRFNode[] = nodes.map((n) => ({
      id: String(n.id),
      type: "explore",
      position: pos.get(n.id) ?? { x: 0, y: 0 },
      data: { node: n },
      selected: n.id === selectedId,
    }));
    const rfEdges: RFEdge[] = edges.map((e) => ({
      id: `${e.source}-${e.rel}-${e.target}`,
      source: String(e.source),
      target: String(e.target),
      animated: e.rel === "spawns" && nodes.find((n) => n.id === e.target)?.state === "running",
      style: { stroke: relColor[e.rel], strokeWidth: 1.5, strokeDasharray: e.rel === "derived_from" ? "5 4" : undefined },
      markerEnd: { type: MarkerType.ArrowClosed, color: relColor[e.rel], width: 14, height: 14 },
    }));
    return { rfNodes, rfEdges };
  }, [nodes, edges, selectedId]);

  return (
    <ReactFlow
      nodes={rf.rfNodes}
      edges={rf.rfEdges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, n) => onSelect(Number(n.id))}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      minZoom={0.1}
      maxZoom={1.6}
      nodesConnectable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => typeMeta[(n.data as { node: GraphNode }).node.kind as keyof typeof typeMeta]?.hex ?? "#999"}
        className="!bg-background"
      />
      <Panel position="top-left">
        <div className="flex flex-wrap gap-3 rounded-lg border bg-background/90 px-3 py-2 text-xs shadow-sm backdrop-blur">
          {Object.entries(typeMeta).map(([k, m]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-sm", m.iconBg)} />
              {m.label}
            </span>
          ))}
          <span className="text-muted-foreground">·</span>
          {Object.entries(relLabel).map(([k, l]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span className="h-0.5 w-4" style={{ background: relColor[k] }} />
              {l}
            </span>
          ))}
        </div>
      </Panel>
    </ReactFlow>
  );
}

export function ExplorationGraph(props: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <ReactFlowProvider>
      <GraphInner {...props} />
    </ReactFlowProvider>
  );
}
