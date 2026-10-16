"""Streamlit interface for InvoicePilotBR."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from src.ai_extractor import ExtractionError, check_ollama_connection, extract_expense
from src.config import settings
from src.document_reader import (
    DocumentReadError,
    content_fingerprint,
    extract_text,
)
from src.exporter import export_approved_records
from src.models import ExpenseRecord
from src.validator import (
    ExpenseValidationError,
    normalize_document_date,
    parse_amount,
    validate_expense_record,
)

CATEGORY_LABELS = {
    "food": "Alimentação",
    "transportation": "Transporte",
    "software": "Software",
    "office_supplies": "Material de escritório",
    "utilities": "Contas e serviços",
    "healthcare": "Saúde",
    "taxes": "Impostos",
    "other": "Outros",
    "unknown": "Desconhecida",
}

st.set_page_config(page_title="InvoicePilotBR", page_icon="🧾", layout="wide")
st.title("InvoicePilotBR")
st.subheader("Organize seus comprovantes com IA local, mantendo seus documentos no seu computador.")
st.info(
    "A extração por IA pode conter erros. Confira todos os dados antes de confirmar. "
    "Este aplicativo não oferece orientação contábil, fiscal ou jurídica."
)

if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "editor_data" not in st.session_state:
    st.session_state.editor_data = None
if "ollama_status" not in st.session_state:
    st.session_state.ollama_status = check_ollama_connection()

with st.sidebar:
    st.header("Configuração")
    connected, connection_message = st.session_state.ollama_status
    if connected:
        st.success(connection_message)
    else:
        st.warning(connection_message)
    st.caption(f"Modelo configurado: `{settings.ollama_model}`")
    if st.button("Verificar conexão com Ollama"):
        st.session_state.ollama_status = check_ollama_connection()
        st.rerun()
    st.markdown(
        "Os documentos são processados localmente e não são enviados a serviços externos. "
        "Para inferência, inicie o Ollama e baixe manualmente o modelo com "
        "`ollama pull qwen3:4b`."
    )
    st.markdown(
        "Instale as dependências Python com `pip install -r requirements.txt`. "
        "Para OCR, também é necessário instalar Tesseract e o pacote de idioma português."
    )

st.header("Adicionar comprovantes")
uploads = st.file_uploader(
    "Selecione documentos PDF, PNG ou JPG/JPEG",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    help=(
        f"Até {settings.max_files_per_batch} arquivos por lote; "
        f"máximo de {settings.max_file_size_mb} MB por arquivo."
    ),
)

if st.button("Processar documentos", type="primary", disabled=not uploads):
    if len(uploads) > settings.max_files_per_batch:
        st.error(f"O limite é de {settings.max_files_per_batch} arquivos por lote.")
    else:
        seen = set()
        progress = st.progress(0)
        status = st.empty()
        for index, uploaded in enumerate(uploads):
            status.write(f"Processando {uploaded.name}…")
            content = uploaded.getvalue()
            if len(content) > settings.max_file_size_mb * 1024 * 1024:
                st.error(f"{uploaded.name}: excede o limite de tamanho configurado.")
            elif content_fingerprint(content) in seen:
                st.warning(f"{uploaded.name}: arquivo duplicado neste lote; ignorado.")
            else:
                seen.add(content_fingerprint(content))
                try:
                    document_text = extract_text(uploaded.name, content)
                    with st.spinner(
                        "Analisando localmente com Ollama; o tempo depende do modelo e do computador…"
                    ):
                        record = extract_expense(document_text, uploaded.name)
                    st.session_state.expenses.append(record)
                    st.success(f"{uploaded.name}: texto extraído e dados organizados.")
                except DocumentReadError as error:
                    st.error(f"{uploaded.name}: {error}")
                except ExtractionError as error:
                    st.error(f"{uploaded.name}: {error}")
            progress.progress((index + 1) / len(uploads))
        status.empty()
        st.session_state.editor_data = None
        st.session_state.pop("expense_editor", None)


def _amount_for_display(amount: Decimal | None) -> str:
    if amount is None:
        return ""
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _record_rows(records: list[ExpenseRecord]) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append(
            {
                "id": record.id,
                "arquivo": record.source_filename,
                "fornecedor": record.supplier or "",
                "data": record.document_date.isoformat() if record.document_date else "",
                "valor (R$)": _amount_for_display(record.amount),
                "moeda": record.currency,
                "categoria": CATEGORY_LABELS[record.category],
                "descrição": record.description or "",
                "requer revisão": record.needs_review,
                "observações": record.review_notes or "",
                "incluir": True,
                "confirmado": False,
            }
        )
    return pd.DataFrame(rows)


def _updated_record(record: ExpenseRecord, row: pd.Series) -> ExpenseRecord:
    category_lookup = {label: key for key, label in CATEGORY_LABELS.items()}
    try:
        date_value = normalize_document_date(str(row["data"]).strip())
        amount_text = str(row["valor (R$)"]).strip()
        amount = parse_amount(amount_text)
        return validate_expense_record(
            {
                **record.model_dump(),
                "supplier": str(row["fornecedor"]).strip() or None,
                "document_date": date_value,
                "amount": amount,
                "currency": str(row["moeda"]).strip().upper(),
                "category": category_lookup[str(row["categoria"])],
                "description": str(row["descrição"]).strip() or None,
                "review_notes": str(row["observações"]).strip() or None,
            },
            default_currency=settings.default_currency,
        )
    except (ExpenseValidationError, InvalidOperation, ValueError, KeyError) as error:
        raise ExpenseValidationError("Corrija os campos inválidos desta linha antes de exportar.") from error


if st.session_state.expenses:
    st.header("Revisar despesas")
    if st.session_state.editor_data is None:
        st.session_state.editor_data = _record_rows(st.session_state.expenses)
    edited = st.data_editor(
        st.session_state.editor_data,
        key="expense_editor",
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        column_config={
            "id": None,
            "arquivo": st.column_config.TextColumn("Arquivo", disabled=True),
            "fornecedor": st.column_config.TextColumn("Fornecedor"),
            "data": st.column_config.TextColumn("Data (AAAA-MM-DD ou DD/MM/AAAA)"),
            "valor (R$)": st.column_config.TextColumn("Valor (R$)"),
            "moeda": st.column_config.TextColumn("Moeda"),
            "categoria": st.column_config.SelectboxColumn(
                "Categoria", options=list(CATEGORY_LABELS.values()), required=True
            ),
            "descrição": st.column_config.TextColumn("Descrição"),
            "requer revisão": st.column_config.CheckboxColumn("Requer revisão", disabled=True),
            "observações": st.column_config.TextColumn("Observações", disabled=True),
            "incluir": st.column_config.CheckboxColumn("Incluir na exportação"),
            "confirmado": st.column_config.CheckboxColumn("Revisei e confirmo"),
        },
    )
    st.session_state.editor_data = edited.copy()

    updated_records = []
    approved_ids = set()
    validation_errors = []
    invalid_ids = set()
    records_by_id = {record.id: record for record in st.session_state.expenses}
    for _, row in edited.iterrows():
        record_id = str(row["id"])
        old_record = records_by_id.get(record_id)
        if old_record is None:
            continue
        try:
            updated = _updated_record(old_record, row)
            updated_records.append(updated)
            if bool(row["incluir"]):
                if bool(row["confirmado"]):
                    approved_ids.add(updated.id)
        except ExpenseValidationError:
            updated_records.append(old_record)
            validation_errors.append(str(row["arquivo"]))
            invalid_ids.add(record_id)
    st.session_state.expenses = updated_records
    if validation_errors:
        st.warning(
            "Há campos inválidos em: " + ", ".join(validation_errors) +
            ". Corrija-os na tabela para salvar as alterações e exportar."
        )

    totals: dict[str, Decimal] = {}
    for record in updated_records:
        row = edited.loc[edited["id"] == record.id]
        if (
            not row.empty
            and bool(row.iloc[0]["incluir"])
            and bool(row.iloc[0]["confirmado"])
            and record.id not in invalid_ids
            and record.amount is not None
        ):
            totals[record.currency] = totals.get(record.currency, Decimal("0")) + record.amount
    needs_review_count = sum(record.needs_review for record in updated_records)
    st.markdown(
        f"**Documentos processados:** {len(updated_records)} &nbsp; | &nbsp; "
        f"**Registros que requerem revisão:** {needs_review_count}"
    )
    if totals:
        total_text = " · ".join(
            f"{currency} {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            for currency, amount in sorted(totals.items())
        )
        st.markdown(f"**Total confirmado por moeda:** {total_text}")
    else:
        st.markdown("**Total confirmado por moeda:** nenhum valor aprovado")

    csv_data = export_approved_records(updated_records, approved_ids)
    st.download_button(
        "Exportar registros confirmados para CSV",
        data=csv_data.encode("utf-8"),
        file_name="invoicepilotbr_despesas.csv",
        mime="text/csv; charset=utf-8",
        disabled=not approved_ids or bool(validation_errors),
        help="Somente linhas incluídas e marcadas como revisadas e confirmadas serão exportadas.",
    )
