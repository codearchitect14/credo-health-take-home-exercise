import { useEffect, useState } from "react";
import { fetchPatient } from "../api";

export default function PatientDetail({ patientId, onBack }) {
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadPatient() {
      setLoading(true);
      setError("");
      setPatient(null);
      try {
        const data = await fetchPatient(patientId);
        if (!cancelled) {
          setPatient(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadPatient();
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  return (
    <section>
      <button className="back" onClick={onBack}>
        ← Back to patients
      </button>

      {loading && <p>Loading patient...</p>}
      {error && <p className="error">{error}</p>}

      {patient && (
        <>
          <h2>{patient.full_name || "Unknown Patient"}</h2>
          <dl className="meta">
            <dt>FHIR ID</dt>
            <dd>{patient.fhir_id}</dd>
            <dt>Gender</dt>
            <dd>{patient.gender}</dd>
            <dt>Birth Date</dt>
            <dd>{patient.birth_date || "N/A"}</dd>
            <dt>MRN</dt>
            <dd>{patient.mrn || "N/A"}</dd>
          </dl>

          <h3>Observations ({patient.observations.length})</h3>
          {patient.observations.length > 0 ? (
            <table className="obs-table">
              <thead>
                <tr>
                  <th>Display</th>
                  <th>Code</th>
                  <th>Value</th>
                  <th>Status</th>
                  <th>Effective</th>
                </tr>
              </thead>
              <tbody>
                {patient.observations.map((obs) => (
                  <tr key={obs.id}>
                    <td>{obs.display || "—"}</td>
                    <td>{obs.code || "—"}</td>
                    <td>
                      {obs.value_numeric != null
                        ? `${obs.value_numeric} ${obs.unit}`
                        : obs.value_text || "—"}
                    </td>
                    <td>{obs.status}</td>
                    <td>{obs.effective_at || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No observations for this patient.</p>
          )}
        </>
      )}
    </section>
  );
}
