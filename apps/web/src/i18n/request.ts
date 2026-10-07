import { getRequestConfig } from "next-intl/server";

// English only for now; locale routing arrives with the first translation (plan W1: next-intl, en).
export default getRequestConfig(async () => ({
  locale: "en",
  timeZone: "Africa/Nairobi",
  messages: (await import("../../messages/en.json")).default,
}));
