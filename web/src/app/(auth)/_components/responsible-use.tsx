// The terms shown at sign-in and first-run setup.
export function ResponsibleUse() {
  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <p>
        ZeaLead reads public posts through official APIs and search engines to find people who describe a need your
        product meets. Using it responsibly is your job:
      </p>
      <ul className="list-disc space-y-2 pl-5">
        <li>
          <b>It finds people; it never contacts them.</b> Suggested replies are drafts for a human to read, adapt and
          post. Mass unsolicited messages break platform rules and get accounts banned.
        </li>
        <li>
          <b>Platform terms still apply to you.</b> Reddit and X restrict commercial use of their APIs without an
          agreement. LinkedIn, X, Facebook, Instagram and Threads are never fetched directly.
        </li>
        <li>
          <b>The lead list is personal data.</b> It holds public handles, profile links and quotes. Under GDPR and
          similar laws, keep it for a defined purpose and delete tasks when you are done.
        </li>
        <li>
          Collected posts are written by strangers and can contain instructions aimed at the agents. They are treated
          as data, never as commands, but review leads before acting on them.
        </li>
      </ul>
      <p className="text-muted-foreground">
        ZeaLead is free software under the GNU AGPL-3.0, provided without warranty. If you run a modified version as
        a service for others, you must offer them its source.
      </p>
    </div>
  );
}
