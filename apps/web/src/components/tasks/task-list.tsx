"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ifMatch } from "@/lib/api/fetcher";
import type { TaskOut } from "@/lib/api/generated/model";
import { tasksCreate, tasksList, tasksUpdate } from "@/lib/api/generated/tasks/tasks";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Bucket = "overdue" | "today" | "upcoming" | "none";
const BUCKETS: Bucket[] = ["overdue", "today", "upcoming", "none"];

/** Which bucket a task falls in, using the device's day boundaries (the API uses the agency's timezone). */
export function bucketOf(task: Pick<TaskOut, "due_at">, now = new Date()): Bucket {
  if (!task.due_at) return "none";
  const due = new Date(task.due_at);
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  if (due < start) return "overdue";
  return due < end ? "today" : "upcoming";
}

function TaskRow({ task, onToggle }: { task: TaskOut; onToggle: (task: TaskOut) => Promise<void> }) {
  const t = useTranslations("tasks");
  // Optimistic: the box ticks at once; if saving fails it flips back (the list refetches).
  const [pending, setPending] = useState<boolean | null>(null);
  const done = pending ?? task.status === "done";
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <input
        type="checkbox"
        checked={done}
        onChange={async () => {
          setPending(!done);
          try {
            await onToggle(task);
          } finally {
            setPending(null);
          }
        }}
        aria-label={done ? `${t("reopen")}: ${task.title}` : `${t("markDone")}: ${task.title}`}
        className="mt-1 size-5 shrink-0 accent-[var(--acacia)]"
      />
      <div className="min-w-0 flex-1">
        <p className={cn("font-bold", done && "text-muted-foreground line-through")}>{task.title}</p>
        {task.notes && <p className="text-sm text-muted-foreground">{task.notes}</p>}
      </div>
      {task.due_at && (
        <span className={cn("tabular shrink-0 text-sm", bucketOf(task) === "overdue" && !done ? "font-bold text-destructive" : "text-muted-foreground")}>
          {formatDate(task.due_at)}
        </span>
      )}
    </li>
  );
}

export function TaskList({ entity }: { entity?: { entity_type: string; entity_id: string; label: string } }) {
  const t = useTranslations("tasks");
  const queryClient = useQueryClient();
  const canWrite = useCan("task:write");
  const params = entity ? { entity_type: entity.entity_type, entity_id: entity.entity_id, status: "all" as const } : { status: "open" as const };
  const key = ["tasks", params];
  const tasks = useQuery({ queryKey: key, queryFn: ({ signal }) => tasksList(params, { signal }) });
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tasks"] });

  async function add(event: FormEvent) {
    event.preventDefault();
    await tasksCreate({
      title: title.trim(),
      due_at: due ? new Date(`${due}T09:00:00`).toISOString() : undefined,
      ...(entity ? { entity_type: entity.entity_type, entity_id: entity.entity_id } : {}),
    });
    setTitle("");
    setDue("");
    toast.success(t("created"));
    await refresh();
  }

  async function toggle(task: TaskOut) {
    const completing = task.status !== "done";
    await tasksUpdate(task.id, { done: completing }, ifMatch(task.version));
    if (completing) toast.success(t("markedDone", { title: task.title }));
    await refresh();
  }

  const rows = tasks.data ?? [];
  const grouped = BUCKETS.map((b) => ({ bucket: b, items: rows.filter((r) => r.status === "open" && bucketOf(r) === b) }));
  const done = rows.filter((r) => r.status === "done");

  return (
    <div className="grid gap-6">
      {canWrite && (
        <form onSubmit={add} className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_11rem_auto] sm:items-end">
          <label className="grid gap-1.5 text-sm font-bold">
            {t("add")}
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("placeholder")} className="font-normal" />
          </label>
          <label className="grid gap-1.5 text-sm font-bold">
            {t("due")}
            <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="font-normal" />
          </label>
          <Button type="submit" disabled={!title.trim()}>{t("add")}</Button>
        </form>
      )}
      {rows.length === 0 && !tasks.isPending && <p className="text-muted-foreground">{t("empty")}</p>}
      {grouped.filter((g) => g.items.length).map(({ bucket, items }) => (
        <section key={bucket} aria-labelledby={`bucket-${bucket}`}>
          <h2 id={`bucket-${bucket}`} className={cn("mb-2 text-lg", bucket === "overdue" && "text-destructive")}>
            {t(bucket)} <span className="tabular text-muted-foreground">({items.length})</span>
          </h2>
          <ul className="divide-y rounded-lg border bg-card">
            {items.map((task) => <TaskRow key={task.id} task={task} onToggle={toggle} />)}
          </ul>
        </section>
      ))}
      {done.length > 0 && (
        <section aria-labelledby="bucket-done">
          <h2 id="bucket-done" className="mb-2 text-lg text-muted-foreground">{t("done")}</h2>
          <ul className="divide-y rounded-lg border bg-card">
            {done.map((task) => <TaskRow key={task.id} task={task} onToggle={toggle} />)}
          </ul>
        </section>
      )}
    </div>
  );
}
