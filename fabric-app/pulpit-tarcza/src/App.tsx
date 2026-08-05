import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';

import { AuthPage } from '@/components/AuthPage';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/hooks/AuthContext';
import { ScenarioProvider } from '@/hooks/ScenarioContext';
import { AlertPage } from '@/pages/AlertPage';
import { GeneratorPage } from '@/pages/GeneratorPage';
import { HeatingPage } from '@/pages/HeatingPage';
import { NationalPage } from '@/pages/NationalPage';
import { WelfarePage } from '@/pages/WelfarePage';

function AuthGuard({ children, requireAuth }: { children: ReactNode; requireAuth: boolean }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <div className="text-sm text-slate-500">Wczytywanie…</div>
      </div>
    );
  }

  if (requireAuth && !isAuthenticated) return <Navigate to="/auth" replace />;
  if (!requireAuth && isAuthenticated) return <Navigate to="/" replace />;

  return <>{children}</>;
}

/** Pięć ekranów scenariusza pod wspólnym układem i wspólnym zegarem sceny. */
function Shell({ children }: { children: ReactNode }) {
  return (
    <AuthGuard requireAuth={true}>
      <ScenarioProvider>
        <Layout>{children}</Layout>
      </ScenarioProvider>
    </AuthGuard>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/auth"
          element={
            <AuthGuard requireAuth={false}>
              <AuthPage />
            </AuthGuard>
          }
        />
        <Route
          path="/"
          element={
            <Shell>
              <NationalPage />
            </Shell>
          }
        />
        <Route
          path="/agregaty"
          element={
            <Shell>
              <GeneratorPage />
            </Shell>
          }
        />
        <Route
          path="/wizyty"
          element={
            <Shell>
              <WelfarePage />
            </Shell>
          }
        />
        <Route
          path="/punkty"
          element={
            <Shell>
              <HeatingPage />
            </Shell>
          }
        />
        <Route
          path="/ostrzeganie"
          element={
            <Shell>
              <AlertPage />
            </Shell>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
