import { createAccessControl } from "better-auth/plugins/access";
import { adminAc, defaultStatements, memberAc, ownerAc } from "better-auth/plugins/organization/access";

/** Mirrors apps/auth/src/auth.ts (role keys; what they may do in the API is ADR-0007). */
export const ac = createAccessControl(defaultStatements);
export const roles = {
  owner: ac.newRole(ownerAc.statements),
  admin: ac.newRole(adminAc.statements),
  agent: ac.newRole(memberAc.statements),
  accounts: ac.newRole(memberAc.statements),
  assistant: ac.newRole(memberAc.statements),
  viewer: ac.newRole(memberAc.statements),
};
