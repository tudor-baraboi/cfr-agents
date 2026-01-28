"""Convert DRS Document Types Metadata Mapping Excel to Markdown."""
import openpyxl
from collections import defaultdict
from pathlib import Path

def convert_xlsx_to_markdown():
    xlsx_path = "/Users/tudor/Downloads/DRS Document Types Metadata Mapping.xlsx"
    output_path = Path("/Users/tudor/src/faa-agent/docs/drs-metadata-mapping.md")
    
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["doctype-metdata-mapping"]
    
    # Group by document type
    doc_types = defaultdict(lambda: {"drs_name": "", "service": "", "metadata": [], "sort_by": []})
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        service, drs_name, api_name, meta_drs, meta_api, data_type, is_sort = row
        if api_name:
            doc_types[api_name]["drs_name"] = drs_name
            doc_types[api_name]["service"] = service
            if meta_api:
                doc_types[api_name]["metadata"].append({
                    "drs_name": meta_drs,
                    "api_name": meta_api,
                    "data_type": data_type
                })
            if is_sort:
                doc_types[api_name]["sort_by"].append(meta_api)
    
    # Generate markdown
    lines = []
    lines.append("# DRS Document Types Metadata Mapping")
    lines.append("")
    lines.append("This document maps DRS document types to their API names and metadata fields.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Document Types Summary")
    lines.append("")
    lines.append("| API Name | DRS Name | Service | Metadata Fields |")
    lines.append("|----------|----------|---------|-----------------|")
    
    for api_name in sorted(doc_types.keys()):
        info = doc_types[api_name]
        lines.append(f"| `{api_name}` | {info['drs_name']} | {info['service']} | {len(info['metadata'])} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detailed Metadata by Document Type")
    lines.append("")
    
    for api_name in sorted(doc_types.keys()):
        info = doc_types[api_name]
        lines.append(f"### {api_name}")
        lines.append("")
        lines.append(f"- **DRS Name:** {info['drs_name']}")
        lines.append(f"- **Service:** {info['service']}")
        if info['sort_by']:
            lines.append(f"- **Default Sort By:** `{', '.join(info['sort_by'])}`")
        lines.append("")
        lines.append("| DRS Metadata Name | API Response Name | Data Type |")
        lines.append("|-------------------|-------------------|-----------|")
        for meta in info['metadata']:
            lines.append(f"| {meta['drs_name']} | `{meta['api_name']}` | {meta['data_type']} |")
        lines.append("")
    
    output_path.write_text("\n".join(lines))
    print(f"Created: {output_path}")
    print(f"Document types: {len(doc_types)}")

if __name__ == "__main__":
    convert_xlsx_to_markdown()
