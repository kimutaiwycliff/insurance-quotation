"""Invoice, credit note and payment endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.concurrency import etag
from app.core.permissions import Perm
from app.modules.billing import service
from app.modules.billing.schemas import (
    BillingDocumentOut,
    BillingDocumentSummary,
    BillingSummary,
    ClientAccount,
    CreditNoteCreate,
    DocumentSent,
    EtimsIn,
    FileLink,
    InvoiceCreate,
    InvoiceUpdate,
    Issue,
    PaymentCreate,
    ReceivedPayment,
    SalesQuoteCreate,
    Send,
    Void,
)
from app.platform.deps import ResourcesDep, TenantContext, require_permission
from app.platform.idempotency import Idempotency, idempotency_dependency

router = APIRouter(tags=["billing"])
_write = require_permission(Perm.INVOICE_WRITE)
_issue = require_permission(Perm.INVOICE_ISSUE)
_pay = require_permission(Perm.PAYMENT_WRITE)
Read = Annotated[
    TenantContext, Depends(require_permission((Perm.CLIENT_READ_OWN, Perm.CLIENT_READ_ALL)))
]
Write = Annotated[TenantContext, Depends(_write)]
IssueCtx = Annotated[TenantContext, Depends(_issue)]
Pay = Annotated[TenantContext, Depends(_pay)]
StatusQ = Annotated[
    str | None, Query(pattern="^(draft|unpaid|open|partially_paid|overdue|paid|issued|void)$")
]


async def _out(
    ctx: TenantContext, doc: service.BillingDocument, response: Response
) -> BillingDocumentOut:
    response.headers["ETag"] = etag(doc.version)
    return await service.to_out(ctx, doc)


@router.get("/invoices", operation_id="invoices_list")
async def list_invoices(
    ctx: Read,
    client_id: uuid.UUID | None = None,
    status: StatusQ = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[BillingDocumentSummary]:
    return await service.list_documents(
        ctx, kind="invoice", client_id=client_id, status=status, limit=limit
    )


QuoteStatusQ = Annotated[
    str | None, Query(pattern="^(draft|awaiting|sent|accepted|declined|expired|invoiced|void)$")
]


@router.get("/sales-quotes", operation_id="sales_quotes_list")
async def list_sales_quotes(
    ctx: Read,
    client_id: uuid.UUID | None = None,
    status: QuoteStatusQ = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[BillingDocumentSummary]:
    """Quotes for goods and services (insurance quotes are under /quotes)."""
    return await service.list_documents(
        ctx, kind="quote", client_id=client_id, status=status, limit=limit
    )


@router.post(
    "/sales-quotes",
    operation_id="sales_quotes_create",
    status_code=201,
    response_model=BillingDocumentOut,
)
async def create_sales_quote(
    ctx: Write,
    body: SalesQuoteCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Draft a quote: sections, optional extras, validity. Sending it issues it."""
    if (replay := await idem.replay()) is not None:
        return replay
    doc = await service.create_sales_quote(ctx, body)
    return await idem.respond(201, await service.to_out(ctx, doc), {"ETag": etag(doc.version)})


@router.post(
    "/sales-quotes/{quote_id}/convert", operation_id="sales_quotes_convert", status_code=201
)
async def convert_sales_quote(ctx: IssueCtx, quote_id: uuid.UUID) -> BillingDocumentOut:
    """A draft invoice from the quote, with the extras the client chose."""
    return await service.to_out(ctx, await service.convert_quote(ctx, quote_id))


@router.get("/billing/summary", operation_id="billing_summary")
async def billing_summary(ctx: Read) -> BillingSummary:
    """Outstanding and overdue, ageing, this month's invoicing and collections, quotes awaiting."""
    return await service.billing_summary(ctx)


@router.get("/credit-notes", operation_id="credit_notes_list")
async def list_credit_notes(
    ctx: Read, client_id: uuid.UUID | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> list[BillingDocumentSummary]:
    return await service.list_documents(
        ctx, kind="credit_note", client_id=client_id, status=None, limit=limit
    )


@router.post(
    "/invoices", operation_id="invoices_create", status_code=201, response_model=BillingDocumentOut
)
async def create_invoice(
    ctx: Write,
    body: InvoiceCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_write))],
) -> Response:
    """Create a draft invoice (no number yet)."""
    if (replay := await idem.replay()) is not None:
        return replay
    doc = await service.create_invoice(ctx, body)
    return await idem.respond(201, await service.to_out(ctx, doc), {"ETag": etag(doc.version)})


@router.post(
    "/credit-notes",
    operation_id="credit_notes_create",
    status_code=201,
    response_model=BillingDocumentOut,
)
async def create_credit_note(
    ctx: IssueCtx,
    body: CreditNoteCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_issue))],
) -> Response:
    """Draft a credit note against an issued invoice (all of it, or the lines given)."""
    if (replay := await idem.replay()) is not None:
        return replay
    doc = await service.create_credit_note(ctx, body)
    return await idem.respond(201, await service.to_out(ctx, doc), {"ETag": etag(doc.version)})


@router.get("/billing-documents/{document_id}", operation_id="billing_documents_get")
async def get_document(ctx: Read, document_id: uuid.UUID, response: Response) -> BillingDocumentOut:
    return await _out(ctx, await service.get_document(ctx, document_id), response)


@router.patch("/billing-documents/{document_id}", operation_id="billing_documents_update")
async def update_document(
    ctx: Write,
    document_id: uuid.UUID,
    body: InvoiceUpdate,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> BillingDocumentOut:
    """Edit a draft. Issued documents are corrected with a credit note."""
    return await _out(ctx, await service.update_draft(ctx, document_id, body, if_match), response)


@router.post("/billing-documents/{document_id}/issue", operation_id="billing_documents_issue")
async def issue(
    ctx: IssueCtx, document_id: uuid.UUID, body: Issue, response: Response
) -> BillingDocumentOut:
    """Number it, freeze it and post it to the ledger."""
    return await _out(ctx, await service.issue(ctx, document_id, body), response)


@router.post("/billing-documents/{document_id}/void", operation_id="billing_documents_void")
async def void(
    ctx: IssueCtx, document_id: uuid.UUID, body: Void, response: Response
) -> BillingDocumentOut:
    return await _out(ctx, await service.void(ctx, document_id, body), response)


@router.put("/billing-documents/{document_id}/etims", operation_id="billing_documents_etims")
async def record_etims(
    ctx: IssueCtx, document_id: uuid.UUID, body: EtimsIn, response: Response
) -> BillingDocumentOut:
    """Record the KRA eTIMS CU invoice number (and verification link) from your own eTIMS tool."""
    return await _out(ctx, await service.record_etims(ctx, document_id, body), response)


@router.post("/billing-documents/{document_id}/send", operation_id="billing_documents_send")
async def send(
    ctx: IssueCtx, document_id: uuid.UUID, body: Send, resources: ResourcesDep
) -> DocumentSent:
    doc, url, emailed, whatsapp = await service.send(
        ctx,
        document_id,
        body,
        settings=resources.settings,
        storage=resources.storage,
        renderer=resources.pdf_renderer,
    )
    return DocumentSent(
        document=await service.to_out(ctx, doc), url=url, emailed_to=emailed, whatsapp_url=whatsapp
    )


@router.get("/billing-documents/{document_id}/pdf", operation_id="billing_documents_pdf")
async def pdf(ctx: Read, document_id: uuid.UUID, resources: ResourcesDep) -> FileLink:
    return FileLink(
        url=await service.pdf_url(
            ctx,
            document_id,
            settings=resources.settings,
            storage=resources.storage,
            renderer=resources.pdf_renderer,
        )
    )


@router.post("/invoices/{invoice_id}/apply-credit", operation_id="invoices_apply_credit")
async def apply_credit(ctx: Pay, invoice_id: uuid.UUID, response: Response) -> BillingDocumentOut:
    """Use the client's unapplied payments and credit notes to pay this invoice."""
    return await _out(ctx, await service.apply_credit(ctx, invoice_id), response)


@router.get("/payments", operation_id="payments_list")
async def list_payments(
    ctx: Read, client_id: uuid.UUID | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> list[ReceivedPayment]:
    return await service.list_payments(ctx, client_id=client_id, limit=limit)


@router.post(
    "/payments", operation_id="payments_create", status_code=201, response_model=ReceivedPayment
)
async def record_payment(
    ctx: Pay,
    body: PaymentCreate,
    idem: Annotated[Idempotency, Depends(idempotency_dependency(_pay))],
) -> Response:
    """Record money the client paid into your account; it is applied to their invoices, oldest first."""
    if (replay := await idem.replay()) is not None:
        return replay
    payment = await service.record_payment(ctx, body)
    return await idem.respond(201, await service.payment_out(ctx, payment))


@router.get("/payments/{payment_id}", operation_id="payments_get")
async def get_payment(ctx: Read, payment_id: uuid.UUID) -> ReceivedPayment:
    return await service.payment_out(ctx, await service.get_payment(ctx, payment_id))


@router.post("/payments/{payment_id}/void", operation_id="payments_void")
async def void_payment(ctx: Pay, payment_id: uuid.UUID, body: Void) -> ReceivedPayment:
    return await service.payment_out(ctx, await service.void_payment(ctx, payment_id, body))


@router.get("/payments/{payment_id}/receipt", operation_id="payments_receipt")
async def receipt(ctx: Read, payment_id: uuid.UUID, resources: ResourcesDep) -> FileLink:
    return FileLink(
        url=await service.receipt_url(
            ctx,
            payment_id,
            settings=resources.settings,
            storage=resources.storage,
            renderer=resources.pdf_renderer,
        )
    )


@router.get("/clients/{client_id}/account", operation_id="clients_account")
async def client_account(ctx: Read, client_id: uuid.UUID) -> ClientAccount:
    """What the client owes (from the ledger), their unapplied credit and open invoices."""
    return await service.client_account(ctx, client_id)
