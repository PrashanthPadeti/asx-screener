import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Star } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: "Lessons from the World's Best Multibagger Investors | ASX Screener",
  description:
    'What Peter Lynch, Warren Buffett, Charlie Munger, Philip Fisher, Joel Greenblatt, Terry Smith and others have in common — and what ASX investors can learn from them.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/lessons-from-successful-multibagger-investors' },
}

const INVESTORS = [
  {
    name: 'Peter Lynch',
    role: 'Manager, Fidelity Magellan Fund',
    philosophy: 'Invest in what you understand',
    detail: 'Lynch believed ordinary investors have a natural edge over institutions — they can spot great businesses through everyday observation before Wall Street does. He focused on companies with strong growth potential, simple business models, reasonable debt, good earnings growth, and the patience to let winners grow.',
    lesson: 'Look for companies you understand, then check whether the numbers support the story. If you notice a product or service becoming more popular, verify it with sales growth, profit growth, and valuation before buying.',
    screen: 'revenue_cagr_5y > 10, eps_cagr_5y > 10, pe_ratio < 25, debt_to_equity < 0.5',
  },
  {
    name: 'Thomas Rowe Price Jr.',
    role: 'Founder, T. Rowe Price',
    philosophy: 'Focus on long-term growth',
    detail: 'Price is often called the father of growth investing. He looked for companies that could grow earnings for a long time — with strong earnings growth, high profit margins, strong management, durable business advantages, and long-term industry growth as prerequisites.',
    lesson: 'A company growing revenue and profits consistently for 5, 7, or 10 years is more interesting than one that had one lucky year. Consistency of growth is the strongest signal.',
    screen: 'eps_cagr_10y > 10, revenue_cagr_10y > 10, avg_operating_margin_5y > 15',
  },
  {
    name: 'Philip Fisher',
    role: 'Author, Common Stocks and Uncommon Profits',
    philosophy: 'Study the business deeply',
    detail: 'Fisher believed deeply in understanding a company before investing — going far beyond the numbers to assess management quality, innovation capability, sales organisation strength, and long-term growth opportunity. He was famous for holding positions for decades.',
    lesson: 'Numbers are important but not sufficient. Before buying, ask: Why can this company keep growing? What makes it better than competitors? Can management execute for many years? If you cannot answer these questions, you cannot hold through volatility.',
    screen: 'avg_roic_5y > 15, gross_margin > 40, eps_cagr_5y > 10, piotroski_f_score >= 7',
  },
  {
    name: 'Warren Buffett',
    role: 'Chairman, Berkshire Hathaway',
    philosophy: 'Buy wonderful businesses at fair prices',
    detail: 'Buffett\'s approach evolved from pure value investing toward quality investing — focused on businesses with strong economic moats (competitive advantages), consistent earnings, high return on capital, trustworthy management, strong cash flow, and reasonable valuation. He holds for decades.',
    lesson: 'It is better to buy a great business at a fair price than a poor business at a cheap price. A company with strong ROE, strong cash flow, low debt, and a durable brand may deserve deeper research even if it does not look extremely cheap.',
    screen: 'avg_roe_5y > 15, avg_roce_5y > 15, net_debt_to_ebitda < 1.5, fcf_conversion > 0.8',
  },
  {
    name: 'Charlie Munger',
    role: 'Vice Chairman, Berkshire Hathaway',
    philosophy: 'Quality and patience above all',
    detail: 'Munger is known for applying mental models from multiple disciplines to investing decisions, and for his emphasis on patience and discipline. He believes great investing comes from buying high-quality businesses when opportunities appear — then doing nothing.',
    lesson: 'The big money is made by sitting patiently in great businesses, not by constantly trading. A strong company may look boring for years, but if it keeps growing earnings and reinvesting well, it can compound quietly into something extraordinary.',
    screen: 'avg_roic_5y > 15, eps_cagr_5y > 10, gross_margin > 35, market_cap > 500',
  },
  {
    name: 'Joel Greenblatt',
    role: 'Author, The Little Book That Beats the Market',
    philosophy: 'Quality plus value — the magic formula',
    detail: 'Greenblatt is known for his "magic formula" — combining business quality (measured by return on capital) with valuation (measured by earnings yield). He demonstrated that systematically buying high-quality businesses at reasonable prices outperforms the market over long periods.',
    lesson: 'A strong company is more attractive when it is available at a reasonable price. Do not look only for growth — also check whether the price already reflects that growth. The best opportunities are where quality and value overlap.',
    screen: 'avg_roce_5y > 15, pe_ratio < 20, peg_ratio < 1.5, eps_cagr_5y > 10',
  },
  {
    name: 'Terry Smith',
    role: 'Founder, Fundsmith',
    philosophy: 'Buy good companies, don\'t overpay, do nothing',
    detail: 'Smith runs one of the UK\'s best-known equity funds on a deceptively simple philosophy. He focuses on high-quality companies with strong returns on capital, recurring revenue, strong margins, and low capital intensity — then holds them for the very long term.',
    lesson: 'Great companies that keep earning high returns can create wealth over time if bought at sensible prices. Look for strong margins, high ROE or ROCE, consistent revenue, and the ability to grow without needing too much debt.',
    screen: 'avg_roe_5y > 15, gross_margin > 40, avg_operating_margin_5y > 15, debt_to_equity < 0.5, fcf_conversion > 0.8',
  },
  {
    name: 'Mohnish Pabrai',
    role: 'Founder, Pabrai Investment Funds',
    philosophy: 'Low risk, high uncertainty',
    detail: 'Pabrai is known for his value investing approach and the concept of finding situations with limited downside but large upside potential — the "Dhandho" framework. He also popularised the idea of "cloning" — systematically studying and learning from the best investors.',
    lesson: 'Before buying, ask: What can I lose if I am wrong? Is the balance sheet strong enough to survive bad outcomes? Is the stock already pricing in too much optimism? A good investment protects against the downside as much as it captures the upside.',
    screen: 'piotroski_f_score >= 6, net_debt_to_ebitda < 1.5, pe_ratio < 20, ocf_positive = true',
  },
  {
    name: 'Rakesh Jhunjhunwala',
    role: 'Indian investor and market legend',
    philosophy: 'Back growth with conviction',
    detail: 'Jhunjhunwala, one of India\'s best-known investors, often focused on businesses with large growth potential, capable management, and the structural tailwind of India\'s economic expansion. He was known for taking large concentrated positions in businesses he deeply understood and holding them through volatile periods.',
    lesson: 'A stock may not move immediately after you buy it. If the business keeps improving, patience can matter more than short-term price movement. Multibaggers often need both business growth and investor patience.',
    screen: 'revenue_cagr_5y > 15, eps_cagr_5y > 15, avg_roe_5y > 15, market_cap < 5000',
  },
  {
    name: 'Li Lu',
    role: 'Founder, Himalaya Capital',
    philosophy: 'Think like a business owner, not a trader',
    detail: 'Li Lu, one of the few investors Charlie Munger has consistently praised, is known for deep fundamental research, long-term ownership, and the discipline to hold positions for many years. He treats each investment as if he is buying the whole business.',
    lesson: 'Do not think like a short-term trader when searching for multibaggers. Ask yourself: Would I be happy owning the entire business for 10 years, through good times and bad? If the answer is no, the research process is not complete.',
    screen: 'avg_roic_5y > 15, revenue_cagr_5y > 10, piotroski_f_score >= 7, net_debt_to_ebitda < 2',
  },
]

const COMMON_LESSONS = [
  { n: 1, title: 'Look for growth', detail: 'Sales growth, profit growth, EPS growth, cash flow growth, industry growth. A company cannot become much bigger if the business itself is not growing.' },
  { n: 2, title: 'Look for quality', detail: 'Growth alone is not enough. Check ROE, ROCE, ROIC, operating margin, free cash flow, and debt levels. A high-quality company can grow without destroying shareholder value.' },
  { n: 3, title: 'Look for consistency', detail: 'One good year is not enough. Great investors look for 5-year, 7-year, and 10-year track records. Consistency reduces the chance that growth was temporary.' },
  { n: 4, title: 'Understand the business', detail: 'Do not buy just because numbers look good. Ask: What does the company do? How does it make money? Why do customers choose it? Can it keep growing? What can go wrong?' },
  { n: 5, title: 'Check debt and risk', detail: 'High debt can destroy a growth story. Check debt-to-equity, interest coverage, cash flow, and capital raising history. A weak balance sheet is a hidden risk in any growth story.' },
  { n: 6, title: 'Do not overpay', detail: 'Even a great company can be a poor investment if bought at a very expensive price. Check P/E, EV/EBITDA, price-to-sales, FCF yield, and valuation relative to growth and peers.' },
  { n: 7, title: 'Be patient', detail: 'Most multibaggers take years, not weeks. They do not usually become 5× or 10× stocks quickly. Patience is the most underrated investing skill — and the hardest to practise.' },
]

export default function LessonsFromMultibaggerInvestorsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="Lessons from the World's Best Multibagger Investors"
        description="What Peter Lynch, Warren Buffett, Charlie Munger, Philip Fisher, Joel Greenblatt, Terry Smith and others have in common — and what ASX investors can learn from them."
        url="https://asxscreener.com.au/learn/lessons-from-successful-multibagger-investors"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: "Lessons from the World's Best Multibagger Investors", href: '/learn/lessons-from-successful-multibagger-investors' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">Intermediate</span>
          <span className="text-xs text-slate-400">12 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Lessons from the World&apos;s Best Multibagger Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Peter Lynch, Warren Buffett, Charlie Munger, Philip Fisher, Joel Greenblatt, Terry Smith — each had a different style, a different era, a different market. Yet their lessons about finding multibagger stocks converge on the same core principles. Here is what they found, and what it means for ASX investors today.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-purple-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Apply These Investors&apos; Principles</p>
          <p className="text-purple-200 text-sm">Screen ASX stocks by ROIC, ROCE, EPS CAGR, FCF, PEG and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-5 flex items-center gap-2">
          <Star className="w-5 h-5 text-amber-500" /> 10 great investors — their approach and ASX screen
        </h2>
        <div className="space-y-5">
          {INVESTORS.map(({ name, role, philosophy, detail, lesson, screen }) => (
            <div key={name} className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
                <div>
                  <p className="font-bold text-slate-900">{name}</p>
                  <p className="text-xs text-slate-400">{role}</p>
                </div>
                <span className="text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded-full shrink-0">{philosophy}</span>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed mb-3">{detail}</p>
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 mb-3">
                <p className="text-xs font-semibold text-blue-800 mb-1">Key lesson</p>
                <p className="text-xs text-blue-900 leading-relaxed">{lesson}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-500 mb-1">Inspired screen</p>
                <div className="bg-slate-900 rounded-lg p-2">
                  <code className="text-emerald-300 font-mono text-xs">{screen}</code>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">7 lessons they all share</h2>
        <p className="text-slate-500 text-sm mb-4">Despite different styles and different eras, these investors&apos; principles converge on the same core ideas:</p>
        <div className="space-y-3">
          {COMMON_LESSONS.map(({ n, title, detail }) => (
            <div key={n} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-purple-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{n}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{title}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 rounded-2xl p-6">
        <p className="text-slate-300 text-sm leading-relaxed mb-3">The biggest lesson from all of them, expressed simply:</p>
        <p className="text-white font-bold text-base leading-relaxed">
          &quot;Find strong businesses early, understand them deeply, buy at sensible prices, and give them time to grow.&quot;
        </p>
        <p className="text-slate-400 text-xs mt-3">
          Multibagger investing is not about chasing hot tips. It is about combining growth, quality, strong management, financial discipline, reasonable valuation, and patience — then letting compounding do its work.
        </p>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/what-is-a-multibagger-stock', label: 'What Is a Multibagger Stock?' },
            { href: '/learn/how-to-screen-for-asx-multibagger-stocks', label: 'How to Screen for ASX Multibagger Stocks' },
            { href: '/learn/how-to-find-quality-asx-companies', label: 'How to Find Quality ASX Companies' },
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Historical investor strategies do not guarantee future results. All investing involves risk. Always conduct your own research before making any investment decision.</p>
      </div>
    </div>
  )
}
