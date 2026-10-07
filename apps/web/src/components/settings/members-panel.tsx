"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Field } from "@/components/forms/field";
import { useMe } from "@/components/shell/me-context";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useRolesList } from "@/lib/api/generated/members/members";
import { authClient } from "@/lib/auth-client";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  agent: "Agent",
  accounts: "Accounts",
  assistant: "Assistant",
  viewer: "Viewer",
};
const INVITABLE = ["agent", "assistant", "accounts", "admin", "viewer"] as const;

export function MembersPanel() {
  const t = useTranslations("members");
  const me = useMe();
  const org = authClient.useActiveOrganization();
  const roles = useRolesList();
  const canManage = me.role === "owner" || me.role === "admin";
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<(typeof INVITABLE)[number]>("agent");
  const [busy, setBusy] = useState(false);

  const refresh = () => org.refetch();

  async function invite(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const { error } = await authClient.organization.inviteMember({ email: email.trim(), role });
    setBusy(false);
    if (error) {
      toast.error(error.message ?? "The invitation was not sent. Check the email address.");
      return;
    }
    toast.success(t("invited", { email }));
    setEmail("");
    await refresh();
  }

  async function changeRole(memberId: string, next: string) {
    const { error } = await authClient.organization.updateMemberRole({ memberId, role: next });
    if (error) toast.error(error.message ?? "The role was not changed.");
    else toast.success(t("roleChanged"));
    await refresh();
  }

  async function remove(memberId: string, name: string) {
    const { error } = await authClient.organization.removeMember({ memberIdOrEmail: memberId });
    if (error) toast.error(error.message ?? "This person was not removed.");
    else toast.success(t("removed", { name }));
    await refresh();
  }

  async function cancelInvite(invitationId: string) {
    await authClient.organization.cancelInvitation({ invitationId });
    await refresh();
  }

  if (!org.data) return <Skeleton className="h-64 w-full" />;
  const pending = (org.data.invitations ?? []).filter((i) => i.status === "pending");

  return (
    <div className="grid gap-10">
      {canManage && (
        <form onSubmit={invite} className="grid gap-4 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_11rem_auto] sm:items-end">
          <Field label={t("inviteEmail")}>
            {(p) => <Input {...p} type="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Field label={t("role")}>
            {(p) => (
              <NativeSelect {...p} value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
                {INVITABLE.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
              </NativeSelect>
            )}
          </Field>
          <Button type="submit" size="lg" disabled={busy || !email}>{t("sendInvite")}</Button>
        </form>
      )}

      <ul className="divide-y rounded-lg border bg-card">
        {org.data.members.map((member) => {
          const self = member.userId === me.user_id;
          const name = member.user.name || member.user.email;
          return (
            <li key={member.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-bold">
                  {name} {self && <span className="font-normal text-muted-foreground">({t("you")})</span>}
                </p>
                <p className="truncate text-sm text-muted-foreground">{member.user.email}</p>
              </div>
              {canManage && !self && member.role !== "owner" ? (
                <NativeSelect
                  aria-label={`${t("role")}: ${name}`}
                  value={member.role}
                  onChange={(e) => changeRole(member.id, e.target.value)}
                  className="h-9 w-36"
                >
                  {INVITABLE.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </NativeSelect>
              ) : (
                <Badge variant="secondary">{ROLE_LABELS[member.role] ?? member.role}</Badge>
              )}
              {canManage && !self && member.role !== "owner" && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="sm" className="text-destructive">{t("remove")}</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogTitle>{t("remove")}</AlertDialogTitle>
                    <AlertDialogDescription>{t("removeConfirm", { name })}</AlertDialogDescription>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Keep</AlertDialogCancel>
                      <AlertDialogAction onClick={() => remove(member.id, name)} className="bg-destructive text-white hover:bg-destructive/90">
                        {t("remove")}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </li>
          );
        })}
        {pending.map((invitation) => (
          <li key={invitation.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-bold">{invitation.email}</p>
              <p className="text-sm text-muted-foreground">{t("pending")}</p>
            </div>
            <Badge variant="outline">{ROLE_LABELS[invitation.role] ?? invitation.role}</Badge>
            {canManage && (
              <Button variant="ghost" size="sm" onClick={() => cancelInvite(invitation.id)}>{t("cancelInvite")}</Button>
            )}
          </li>
        ))}
      </ul>

      <section aria-labelledby="roles-heading">
        <h3 id="roles-heading" className="mb-3 text-xl">{t("roles")}</h3>
        <dl className="grid gap-3 sm:grid-cols-2">
          {(roles.data ?? []).map((r) => (
            <div key={r.key} className="border-l-2 border-maize pl-3">
              <dt className="font-bold">{ROLE_LABELS[r.key] ?? r.key}</dt>
              <dd className="text-sm text-muted-foreground">{r.description}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
