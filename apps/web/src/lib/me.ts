import type { MeOut } from "@/lib/api/generated/model";

export type Me = MeOut;

export function can(me: Pick<Me, "permissions">, permission: string): boolean {
  return (me.permissions as string[]).includes(permission);
}
