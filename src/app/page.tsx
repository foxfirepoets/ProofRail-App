export default function Page() {
  return (
    <main style={{ fontFamily: "Arial, sans-serif", padding: 24, maxWidth: 960 }}>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>ProofRail Operator Status</h1>
      <p style={{ marginTop: 0, color: "#4b5563" }}>
        Cowork remains the working UI. This page is intentionally minimal until the MCP pipeline proves itself.
      </p>
      <section style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
        {[
          ["MCP seam", "Wired"],
          ["Money lock", "Server-side"],
          ["QBO boundary", "Bills / Invoices / JEs only"],
        ].map(([label, value]) => (
          <div key={label} style={{ border: "1px solid #d1d5db", borderRadius: 8, padding: 16 }}>
            <div style={{ color: "#6b7280", fontSize: 12 }}>{label}</div>
            <div style={{ fontSize: 18, marginTop: 4 }}>{value}</div>
          </div>
        ))}
      </section>
    </main>
  );
}
