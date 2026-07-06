import { useState } from "react";
import PatientDetail from "./components/PatientDetail";
import PatientList from "./components/PatientList";

export default function App() {
  const [selectedPatientId, setSelectedPatientId] = useState(null);

  return (
    <div className="app">
      {selectedPatientId ? (
        <PatientDetail
          patientId={selectedPatientId}
          onBack={() => setSelectedPatientId(null)}
        />
      ) : (
        <PatientList onSelectPatient={setSelectedPatientId} />
      )}
    </div>
  );
}
