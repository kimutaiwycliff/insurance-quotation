"""R2.1: invoicing core: item catalogue, invoices and credit notes, payments, allocations, ledger.

Issued documents are immutable (ADR-0009, trigger); journals balance per entry and currency (ADR-0012, deferred
constraint trigger). Allocations and journals are append-only; nothing here can be deleted by app_user.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import append_only, disable_tenant_rls, enable_tenant_rls

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_STATEMENTS = [
    """
    CREATE TABLE app.items (
        name VARCHAR NOT NULL,
        description VARCHAR,
        unit VARCHAR,
        unit_price NUMERIC(20, 4) NOT NULL,
        currency CHAR(3) NOT NULL,
        tax_code VARCHAR NOT NULL,
        active BOOLEAN DEFAULT true NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_items PRIMARY KEY (id),
        CONSTRAINT uq_items_tenant_id_id UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX uq_items_name ON app.items (tenant_id, name)",
    """
    CREATE TABLE app.billing_documents (
        kind VARCHAR NOT NULL,
        number VARCHAR,
        client_id UUID NOT NULL,
        owner_user_id VARCHAR NOT NULL,
        status VARCHAR DEFAULT 'draft' NOT NULL,
        currency CHAR(3) NOT NULL,
        issue_date DATE,
        due_date DATE,
        prices_include_tax BOOLEAN DEFAULT false NOT NULL,
        subtotal NUMERIC(20, 4) DEFAULT '0' NOT NULL,
        discount NUMERIC(20, 4) DEFAULT '0' NOT NULL,
        tax NUMERIC(20, 4) DEFAULT '0' NOT NULL,
        total NUMERIC(20, 4) DEFAULT '0' NOT NULL,
        taxes JSONB DEFAULT '[]'::jsonb NOT NULL,
        pack JSONB DEFAULT '{}'::jsonb NOT NULL,
        payment_reference VARCHAR,
        credits_document_id UUID,
        reference VARCHAR,
        notes VARCHAR,
        terms VARCHAR,
        document_id UUID,
        issued_at TIMESTAMP WITH TIME ZONE,
        issued_by VARCHAR,
        voided_at TIMESTAMP WITH TIME ZONE,
        void_reason VARCHAR,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT pk_billing_documents PRIMARY KEY (id),
        CONSTRAINT uq_billing_documents_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_billing_documents_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id),
        CONSTRAINT fk_billing_documents_tenant_id_document_id_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.documents (tenant_id, id),
        CONSTRAINT fk_billing_documents_tenant_id_credits_document_id_bill_f8cd FOREIGN KEY(tenant_id, credits_document_id) REFERENCES app.billing_documents (tenant_id, id),
        CONSTRAINT ck_billing_documents_kind CHECK (kind IN ('invoice', 'credit_note')),
        CONSTRAINT ck_billing_documents_status CHECK (status IN ('draft', 'issued', 'void'))
    )
    """,
    "CREATE INDEX ix_billing_documents_client ON app.billing_documents (tenant_id, client_id, kind, status)",
    "CREATE INDEX ix_billing_documents_due ON app.billing_documents (tenant_id, status, due_date)",
    "CREATE UNIQUE INDEX uq_billing_documents_number ON app.billing_documents (tenant_id, kind, number)",
    "CREATE UNIQUE INDEX uq_billing_documents_payment_reference ON app.billing_documents (tenant_id, payment_reference)",
    """
    CREATE TABLE app.billing_lines (
        document_id UUID NOT NULL,
        position INTEGER NOT NULL,
        item_id UUID,
        description VARCHAR NOT NULL,
        quantity NUMERIC(20, 4) NOT NULL,
        unit_price NUMERIC(20, 4) NOT NULL,
        discount_rate NUMERIC(12, 8) DEFAULT '0' NOT NULL,
        tax_code VARCHAR NOT NULL,
        tax_rate NUMERIC(12, 8) NOT NULL,
        net NUMERIC(20, 4) NOT NULL,
        tax NUMERIC(20, 4) NOT NULL,
        total NUMERIC(20, 4) NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_billing_lines PRIMARY KEY (id),
        CONSTRAINT uq_billing_lines_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_billing_lines_tenant_id_document_id_position UNIQUE (tenant_id, document_id, position),
        CONSTRAINT fk_billing_lines_tenant_id_document_id_billing_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.billing_documents (tenant_id, id),
        CONSTRAINT fk_billing_lines_tenant_id_item_id_items FOREIGN KEY(tenant_id, item_id) REFERENCES app.items (tenant_id, id)
    )
    """,
    """
    CREATE TABLE app.payments (
        number VARCHAR NOT NULL,
        client_id UUID NOT NULL,
        received_on DATE NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        currency CHAR(3) NOT NULL,
        method VARCHAR NOT NULL,
        reference VARCHAR,
        notes VARCHAR,
        document_id UUID,
        voided_at TIMESTAMP WITH TIME ZONE,
        void_reason VARCHAR,
        voided_by VARCHAR,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_payments PRIMARY KEY (id),
        CONSTRAINT uq_payments_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_payments_tenant_id_client_id_clients FOREIGN KEY(tenant_id, client_id) REFERENCES app.clients (tenant_id, id),
        CONSTRAINT fk_payments_tenant_id_document_id_documents FOREIGN KEY(tenant_id, document_id) REFERENCES app.documents (tenant_id, id),
        CONSTRAINT ck_payments_amount CHECK (amount > 0)
    )
    """,
    "CREATE INDEX ix_payments_client ON app.payments (tenant_id, client_id)",
    "CREATE UNIQUE INDEX uq_payments_number ON app.payments (tenant_id, number)",
    """
    CREATE TABLE app.allocations (
        payment_id UUID,
        credit_note_id UUID,
        invoice_id UUID NOT NULL,
        amount NUMERIC(20, 4) NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_allocations PRIMARY KEY (id),
        CONSTRAINT uq_allocations_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_allocations_tenant_id_payment_id_payments FOREIGN KEY(tenant_id, payment_id) REFERENCES app.payments (tenant_id, id),
        CONSTRAINT fk_allocations_tenant_id_credit_note_id_billing_documents FOREIGN KEY(tenant_id, credit_note_id) REFERENCES app.billing_documents (tenant_id, id),
        CONSTRAINT fk_allocations_tenant_id_invoice_id_billing_documents FOREIGN KEY(tenant_id, invoice_id) REFERENCES app.billing_documents (tenant_id, id),
        CONSTRAINT ck_allocations_amount CHECK (amount > 0),
        CONSTRAINT ck_allocations_one_source CHECK ((payment_id IS NULL) <> (credit_note_id IS NULL))
    )
    """,
    "CREATE INDEX ix_allocations_credit_note ON app.allocations (tenant_id, credit_note_id)",
    "CREATE INDEX ix_allocations_invoice ON app.allocations (tenant_id, invoice_id)",
    "CREATE INDEX ix_allocations_payment ON app.allocations (tenant_id, payment_id)",
    """
    CREATE TABLE app.journal_entries (
        occurred_on DATE NOT NULL,
        source_type VARCHAR NOT NULL,
        source_id UUID NOT NULL,
        memo VARCHAR NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_journal_entries PRIMARY KEY (id),
        CONSTRAINT uq_journal_entries_tenant_id_id UNIQUE (tenant_id, id)
    )
    """,
    "CREATE INDEX ix_journal_entries_source ON app.journal_entries (tenant_id, source_type, source_id)",
    """
    CREATE TABLE app.journal_lines (
        entry_id UUID NOT NULL,
        account VARCHAR NOT NULL,
        debit NUMERIC(20, 4) NOT NULL,
        credit NUMERIC(20, 4) NOT NULL,
        currency CHAR(3) NOT NULL,
        client_id UUID,
        id UUID DEFAULT uuidv7() NOT NULL,
        tenant_id UUID NOT NULL,
        CONSTRAINT pk_journal_lines PRIMARY KEY (id),
        CONSTRAINT uq_journal_lines_tenant_id_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_journal_lines_tenant_id_entry_id_journal_entries FOREIGN KEY(tenant_id, entry_id) REFERENCES app.journal_entries (tenant_id, id),
        CONSTRAINT ck_journal_lines_account CHECK (account IN ('receivable', 'cash', 'client_credit', 'tax_payable', 'revenue')),
        CONSTRAINT ck_journal_lines_one_side CHECK (debit >= 0 AND credit >= 0 AND (debit = 0) <> (credit = 0))
    )
    """,
    "CREATE INDEX ix_journal_lines_account_client ON app.journal_lines (tenant_id, account, client_id)",
    "CREATE INDEX ix_journal_lines_entry ON app.journal_lines (tenant_id, entry_id)",
]

TABLES = [
    "items",
    "billing_documents",
    "billing_lines",
    "payments",
    "allocations",
    "journal_entries",
    "journal_lines",
]

GUARDS = [
    # ADR-0009: an issued or void document only changes through the void transition and bookkeeping columns.
    """
    CREATE FUNCTION app.guard_issued_billing_document() RETURNS trigger
    LANGUAGE plpgsql SET search_path = app, pg_temp AS $$
    BEGIN
        IF OLD.status = 'draft' THEN
            RETURN NEW;
        END IF;
        IF OLD.status = 'void' AND NEW.status <> 'void' THEN
            RAISE EXCEPTION 'a void % cannot be changed', OLD.kind USING ERRCODE = 'check_violation';
        END IF;
        IF (NEW.kind, NEW.number, NEW.client_id, NEW.currency, NEW.issue_date, NEW.due_date,
            NEW.prices_include_tax, NEW.subtotal, NEW.discount, NEW.tax, NEW.total, NEW.taxes,
            NEW.payment_reference, NEW.credits_document_id, NEW.issued_at)
           IS DISTINCT FROM
           (OLD.kind, OLD.number, OLD.client_id, OLD.currency, OLD.issue_date, OLD.due_date,
            OLD.prices_include_tax, OLD.subtotal, OLD.discount, OLD.tax, OLD.total, OLD.taxes,
            OLD.payment_reference, OLD.credits_document_id, OLD.issued_at) THEN
            RAISE EXCEPTION 'issued % % is immutable; correct it with a credit note', OLD.kind, OLD.number
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER billing_documents_immutable BEFORE UPDATE ON app.billing_documents
    FOR EACH ROW EXECUTE FUNCTION app.guard_issued_billing_document()
    """,
    """
    CREATE FUNCTION app.guard_issued_billing_lines() RETURNS trigger
    LANGUAGE plpgsql SET search_path = app, pg_temp AS $$
    DECLARE
        doc_status text;
    BEGIN
        SELECT status INTO doc_status FROM app.billing_documents
         WHERE tenant_id = COALESCE(NEW.tenant_id, OLD.tenant_id)
           AND id = COALESCE(NEW.document_id, OLD.document_id);
        IF doc_status IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'lines of an issued document cannot change' USING ERRCODE = 'check_violation';
        END IF;
        RETURN COALESCE(NEW, OLD);
    END $$
    """,
    """
    CREATE TRIGGER billing_lines_immutable BEFORE INSERT OR UPDATE OR DELETE ON app.billing_lines
    FOR EACH ROW EXECUTE FUNCTION app.guard_issued_billing_lines()
    """,
    # ADR-0012: every journal entry balances per currency, checked at commit.
    """
    CREATE FUNCTION app.check_journal_balanced() RETURNS trigger
    LANGUAGE plpgsql SET search_path = app, pg_temp AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM app.journal_lines
             WHERE tenant_id = NEW.tenant_id AND entry_id = NEW.entry_id
             GROUP BY currency HAVING sum(debit) <> sum(credit)
        ) THEN
            RAISE EXCEPTION 'journal entry % does not balance', NEW.entry_id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NULL;
    END $$
    """,
    """
    CREATE CONSTRAINT TRIGGER journal_lines_balanced AFTER INSERT ON app.journal_lines
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_journal_balanced()
    """,
]


def upgrade() -> None:
    for statement in CREATE_STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        for statement in enable_tenant_rls(table):
            op.execute(statement)
    for statement in GUARDS:
        op.execute(statement)
    # Financial records: issued documents are voided or credited, payments voided, never deleted.
    op.execute(
        "REVOKE DELETE, TRUNCATE ON app.items, app.billing_documents, app.payments FROM app_user"
    )
    op.execute("REVOKE TRUNCATE ON app.billing_lines FROM app_user")
    for table in ("allocations", "journal_entries", "journal_lines"):
        for statement in append_only(table):
            op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journal_lines_balanced ON app.journal_lines")
    op.execute("DROP TRIGGER IF EXISTS billing_lines_immutable ON app.billing_lines")
    op.execute("DROP TRIGGER IF EXISTS billing_documents_immutable ON app.billing_documents")
    op.execute("DROP FUNCTION IF EXISTS app.check_journal_balanced()")
    op.execute("DROP FUNCTION IF EXISTS app.guard_issued_billing_lines()")
    op.execute("DROP FUNCTION IF EXISTS app.guard_issued_billing_document()")
    for table in TABLES:
        for statement in disable_tenant_rls(table):
            op.execute(statement)
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS app.{table}")
