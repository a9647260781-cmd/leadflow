import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, ProtectedRoute } from './auth'
import { LeadDetailPage } from './pages/LeadDetailPage'
import { LeadsPage } from './pages/LeadsPage'
import { LoginPage } from './pages/LoginPage'
import { PublicLeadPage } from './pages/PublicLeadPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<PublicLeadPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/manager" element={<LeadsPage />} />
          <Route path="/manager/leads/:id" element={<LeadDetailPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
