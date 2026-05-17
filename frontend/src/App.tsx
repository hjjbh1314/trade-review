import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { TopNav } from './components/TopNav';
import { TokenGate } from './components/TokenGate';
import { DashboardPage } from './pages/Dashboard';
import { FlashPage } from './pages/Flash';
import { DailyPage } from './pages/Daily';
import { JournalPage } from './pages/Journal';
import { MindsetPage } from './pages/Mindset';

export default function App() {
  return (
    <TokenGate>
      <BrowserRouter>
        <TopNav />
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/flash" element={<FlashPage />} />
          <Route path="/daily" element={<DailyPage />} />
          <Route path="/mindset" element={<MindsetPage />} />
          <Route path="/journal" element={<JournalPage />} />
        </Routes>
      </BrowserRouter>
    </TokenGate>
  );
}
