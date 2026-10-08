import { getTranslations } from "next-intl/server";

import { TaskList } from "@/components/tasks/task-list";

export const metadata = { title: "Tasks" };

export default async function TasksPage() {
  const t = await getTranslations("tasks");
  return (
    <div className="grid gap-5">
      <h1 className="text-3xl">{t("title")}</h1>
      <TaskList />
    </div>
  );
}
