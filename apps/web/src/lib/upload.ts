"use client";

import { documentsCompleteUpload, documentsCreate } from "@/lib/api/generated/documents/documents";
import type { DocumentCreateCategory, DocumentOut } from "@/lib/api/generated/model";

/** Upload a file straight to storage (presigned PUT), then let the API verify it (ADR-0023). */
export async function uploadDocument(file: File, category: DocumentCreateCategory, title?: string): Promise<DocumentOut> {
  const started = await documentsCreate({ filename: file.name, size_bytes: file.size, category, title });
  const put = await fetch(started.upload.url, { method: "PUT", body: file, headers: started.upload.headers });
  if (!put.ok) throw new Error(`Upload failed (${put.status})`);
  return documentsCompleteUpload(started.document.id, started.version_no);
}
