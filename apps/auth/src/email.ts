/** Transactional email (SMTP: Mailpit locally, SES SMTP or similar in production). */
import nodemailer from "nodemailer";

import type { Config } from "./config.js";

export interface Mailer {
  send(to: string, subject: string, text: string): Promise<void>;
}

export function createMailer(config: Config): Mailer {
  const transport = nodemailer.createTransport({
    host: config.smtpHost,
    port: config.smtpPort,
    secure: config.smtpSecure,
    auth: config.smtpUser ? { user: config.smtpUser, pass: config.smtpPassword } : undefined,
  });
  return {
    async send(to, subject, text) {
      await transport.sendMail({ from: config.emailFrom, to, subject, text });
    },
  };
}
