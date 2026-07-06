import { useEffect, useState } from "react";
import { fetchPatients, triggerMigration, waitForRun } from "../api";

export default function PatientList({ onSelectPatient }) {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [migrating, setMigrating] = useState(false);
  const [migrationMessage, setMigrationMessage] = useState("");

  async function loadPatients() {
    setLoading(true);
    setError("");
    try {
      setPatients(await fetchPatients());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runMigration() {
    setMigrating(true);
    setMigrationMessage("");
    setError("");
    try {
      let run = await triggerMigration(20);
      if (run.status === "running") {
        setMigrationMessage("Migration running in background...");
        run = await waitForRun(run.id);
      }
      if (run.status === "failed") {
        throw new Error(run.error_message || "Migration failed.");
      }
      setMigrationMessage(
        `Migrated ${run.patients_migrated} patients and ${run.observations_migrated} observations.`
      );
      await loadPatients();
    } catch (err) {
      setError(err.message);
    } finally {
      setMigrating(false);
    }
  }

  useEffect(() => {
    loadPatients();
  }, []);

  return (
    <section>
      <header className="header">
        <h1>Migrated Patients</h1>
        <button disabled={migrating} onClick={runMigration}>
          {migrating ? "Migrating..." : "Run Migration (20 patients)"}
        </button>
      </header>

      {migrationMessage && <p className="success">{migrationMessage}</p>}
      {error && <p className="error">{error}</p>}
      {loading && <p>Loading patients...</p>}

      {!loading && patients.length > 0 && (
        <ul className="patient-list">
          {patients.map((patient) => (
            <li
              key={patient.id}
              className="patient-item"
              onClick={() => onSelectPatient(patient.id)}
            >
              <strong>{patient.full_name || "Unknown"}</strong>
              <span>
                {patient.gender} · {patient.birth_date || "N/A"}
              </span>
              <span className="muted">{patient.observation_count} observations</span>
            </li>
          ))}
        </ul>
      )}

      {!loading && patients.length === 0 && (
        <p className="muted">
          No patients yet. Click "Run Migration" to fetch data from the FHIR sandbox.
        </p>
      )}
    </section>
  );
}
