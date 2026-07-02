export const dynamic = 'force-dynamic';
export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Analytics</h2>
        <p className="text-gray-500 dark:text-zinc-400">Insights and trends from the Heidi clinical archive.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border bg-white dark:bg-zinc-900 shadow p-6">
          <h3 className="font-bold mb-4">Top Diagnoses</h3>
          <ul className="space-y-2 text-sm">
            <li className="flex justify-between"><span>Hypertension</span> <span className="font-medium text-gray-500">120 cases</span></li>
            <li className="flex justify-between"><span>Type 2 Diabetes</span> <span className="font-medium text-gray-500">85 cases</span></li>
            <li className="flex justify-between"><span>Anxiety</span> <span className="font-medium text-gray-500">64 cases</span></li>
          </ul>
        </div>
        
        <div className="rounded-xl border bg-white dark:bg-zinc-900 shadow p-6">
          <h3 className="font-bold mb-4">Top Medications</h3>
          <ul className="space-y-2 text-sm">
            <li className="flex justify-between"><span>Lisinopril</span> <span className="font-medium text-gray-500">95 mentions</span></li>
            <li className="flex justify-between"><span>Metformin</span> <span className="font-medium text-gray-500">80 mentions</span></li>
            <li className="flex justify-between"><span>Sertraline</span> <span className="font-medium text-gray-500">50 mentions</span></li>
          </ul>
        </div>

        <div className="rounded-xl border bg-white dark:bg-zinc-900 shadow p-6">
          <h3 className="font-bold mb-4">Language Distribution</h3>
          <ul className="space-y-2 text-sm">
            <li className="flex justify-between"><span>English</span> <span className="font-medium text-gray-500">85%</span></li>
            <li className="flex justify-between"><span>Spanish</span> <span className="font-medium text-gray-500">10%</span></li>
            <li className="flex justify-between"><span>Mandarin</span> <span className="font-medium text-gray-500">5%</span></li>
          </ul>
        </div>
      </div>

      <div className="rounded-xl border bg-white dark:bg-zinc-900 shadow p-6 mt-6 h-64 flex items-center justify-center text-gray-400">
        [ Monthly Session Count Chart Placeholder ]
      </div>
    </div>
  )
}

