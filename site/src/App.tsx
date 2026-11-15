import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Home from './pages/Home'
import Features from './pages/Features'
import HowItWorks from './pages/HowItWorks'
import Science from './pages/Science'
import Pricing from './pages/Pricing'
import Docs from './pages/Docs'
import About from './pages/About'
import FAQ from './pages/FAQ'
import Privacy from './pages/Privacy'
import Terms from './pages/Terms'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/features" element={<Features />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/science" element={<Science />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/about" element={<About />} />
        <Route path="/faq" element={<FAQ />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  )
}
