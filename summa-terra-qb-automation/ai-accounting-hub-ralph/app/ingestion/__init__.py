"""Real GC draw-package ingestion (CHUNK_7, SHADOW MODE).

Parses a real draw-package PDF (Hunter's Landing Draw #29 is the golden fixture) into a
canonical DrawPackage + draw_lines, validates totals / retainage / cost-code mappings /
vendors, queues vendor candidates, runs an exception scan, and (when clean + approved) hands
off to the existing shadow fee engine. NO QuickBooks writes, no BillAdd, no payments.
"""
