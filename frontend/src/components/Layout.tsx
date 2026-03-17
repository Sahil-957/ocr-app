import { ReactNode } from "react";

type Props = {
  title: string;
  subtitle: string;
  children: ReactNode;
  onLogout: () => void;
};

export function Layout({ title, subtitle, children, onLogout }: Props) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand-mark">KC</div>
          <h1>Costing OCR</h1>
          <p>Bulk extraction for company costing forms.</p>
        </div>
        <button className="ghost-button" onClick={onLogout}>
          Logout
        </button>
      </aside>
      <main className="content">
        <div className="content-inner">
          <header className="page-header">
            <div>
              <h2>{title}</h2>
              <p>{subtitle}</p>
            </div>
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}
