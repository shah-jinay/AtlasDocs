import { NavLink, Route, Routes } from "react-router-dom";
import { getDevToken, setDevToken } from "./api/client";
import AskPage from "./pages/AskPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import DocumentsPage from "./pages/DocumentsPage";

export default function App() {
  return (
    <div className="app">
      <nav className="top">
        <span className="brand">AtlasDocs</span>
        <NavLink to="/documents" className={({ isActive }) => (isActive ? "active" : "")}>
          Documents
        </NavLink>
        <NavLink to="/ask" className={({ isActive }) => (isActive ? "active" : "")}>
          Ask
        </NavLink>
        <select
          value={getDevToken()}
          onChange={(e) => {
            setDevToken(e.target.value);
            window.location.reload();
          }}
          title="Dev-grade auth: swaps the demo user (see backend/app/core/security.py)"
        >
          <option value="dev-key-alice">alice</option>
          <option value="dev-key-bob">bob</option>
        </select>
      </nav>
      <Routes>
        <Route path="/" element={<DocumentsPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:id" element={<DocumentDetailPage />} />
        <Route path="/ask" element={<AskPage />} />
      </Routes>
    </div>
  );
}
