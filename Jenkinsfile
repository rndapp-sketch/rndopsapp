// CI/CD pipeline for rndopsapp → Testing server (172.17.1.46).
// Tracked branch: testing-backend. See JENKINS_CI_CD_PLAN.md in the bench root.
//
// JOB CONFIG THIS PIPELINE ASSUMES:
//   - "Clean before checkout" / "Wipe out repository" must be DISABLED. Those
//     delete untracked files, which here includes the frontend build output
//     (public/frontend/assets/*, www/rndopsapp.html) written by the
//     prornd-ui-deploy-test job. Cleaning would wipe every frontend deploy.
//
// NOTE ON FIRST RUN: this workspace currently has uncommitted local edits
// (api.py, miscellaneous_commit.py, research_consultancy_deposit_slip.json,
// send_email.py). Jenkins' checkout will overwrite them. Commit or back them
// up BEFORE enabling this job.
//
// Jenkins' own SCM step does the fetch/checkout of testing-backend, so this
// pipeline starts from "new code is already on disk" and only handles the
// Frappe-side work of making the running site pick it up.

// ---------------------------------------------------------------------------
// NOTIFICATIONS  (see DEPLOY_NOTIFICATIONS_PLAN.md in the bench root)
//
// Fires when a merge lands on testing-backend, driven by the DEPLOY rather
// than the merge, because the merge is not the news. On 2026-10-07 merges kept
// landing while the deploy failed on the skip-worktree checkout error; a
// GitHub-side "X merged" message would have told everyone to pull code that
// never reached the server. So the two outcomes say opposite things:
// "rebase" vs "do NOT pull".
//
// Mattermost DMs and email go out in SEPARATE try/catch blocks, so a
// Mattermost outage cannot suppress the email and neither can fail the deploy.
// Telling people about a deploy must never be able to break it.
//
// The message is composed ONCE and handed to both senders. Two copies of a
// message format is how "Testing is stale" ends up saying two different things.
//
// Recipients live in /home/rndadmin/deploy-config/notify-recipients.json, NOT
// in this repo: it is public, and config committed here is overwritten by the
// next deploy. Edit that file when someone joins or leaves - no PR needed.
//
// The recipients path is spelled out in full in each method on purpose. A
// script-level `def CONST` is NOT visible inside a `def method()` in a
// Jenkinsfile - it resolves to null at runtime - and that failure mode stays
// invisible until it fires.
// ---------------------------------------------------------------------------

def notifyAll(String outcome) {
  def msg
  try {
    msg = buildMessage(outcome)
  } catch (e) {
    echo "WARNING: could not compose the notification: ${e}"
    return
  }
  echo "--- notification text ---\n${msg}\n-------------------------"

  try {
    notifyMattermost(msg)
  } catch (e) {
    echo "WARNING: Mattermost notify failed: ${e}"
    // The deploy worked; telling people did not. UNSTABLE says exactly that.
    // Jenkins only ever worsens a result, so this cannot mask a real FAILURE.
    currentBuild.result = 'UNSTABLE'
  }
  try {
    notifyEmail(outcome, msg)
  } catch (e) {
    echo "WARNING: email notify failed: ${e}"
    currentBuild.result = 'UNSTABLE'
  }
}

// Built entirely in the shell and returned as one string. Deliberate: the
// Groovy sandbox rejects more than you would expect - `env[k] = v` cost the
// Live job its build #17 - so this pipeline only passes whole strings around
// and does no array or map manipulation in Groovy.
def buildMessage(String outcome) {
  return sh(returnStdout: true, script: """#!/bin/bash
    set -euo pipefail
    R=/home/rndadmin/deploy-config/notify-recipients.json
    sha=\$(git log -1 --format=%h)
    raw=\$(git log -1 --format=%an)
    subj=\$(git log -1 --format=%s)
    # One person commits under three name spellings and two identities share an
    # address, so map the git name to a real person. Unmapped falls through.
    who=\$(jq -r --arg n "\$raw" '.identities[\$n] // \$n' "\$R")

    if [ '${outcome}' = 'ok' ]; then
      cat <<EOF
testing-backend is updated on Testing (172.17.1.46)

  \$sha  \$who - \$subj
  migrate ok - cache cleared - bench restarted - ping=pong - ${currentBuild.durationString.replace(' and counting', '')}

Pull / rebase your feature branch before your next push.
  ${env.BUILD_URL}
EOF
    else
      cat <<EOF
testing-backend deploy FAILED on Testing (172.17.1.46)

  \$sha  \$who - \$subj
  Testing is still serving the PREVIOUS build. Do NOT pull yet.

  ${env.BUILD_URL}console
EOF
    fi
  """).trim()
}

// DMs each developer individually. A Mattermost incoming webhook accepts
// {"channel": "@username"} to redirect a post into a direct message, so one
// webhook reaches everyone with no channel id and no bot account.
//
// The cost of DMs over a channel, recorded so it stays a known trade: the
// username list has to be maintained in the JSON (a channel would have kept it
// in Mattermost, where joiners and leavers get handled anyway), it is one HTTP
// call per person so partial delivery is possible, and there is no shared
// timeline anyone can scroll to check whether a merge was announced. Setting
// mattermost_channel in the JSON adds a channel post alongside the DMs.
//
// The message goes in through the environment rather than a temp file:
// WORKSPACE_TMP is not guaranteed to be set, and this workspace IS the live
// bench app directory, so stray files here land inside the served app.
def notifyMattermost(String msg) {
  withCredentials([string(credentialsId: 'mattermost-deploy-webhook', variable: 'MM_HOOK')]) {
    withEnv(["NOTIFY_MSG=${msg}"]) {
      sh '''#!/bin/bash
        # No -e: one failed DM must not abort the rest of the loop.
        set -uo pipefail
        R=/home/rndadmin/deploy-config/notify-recipients.json

        # Force a leading @ on every DM target. Mattermost's webhook "channel"
        # field treats a bare name as a CHANNEL and only an @-prefixed one as a
        # direct message, so a bare entry either fails to deliver or posts into
        # an unrelated channel that happens to share the name. Five of the
        # first eight entries written by hand were bare, so normalising here
        # rather than trusting the file is the difference between working and
        # silently not.
        mapfile -t targets < <(jq -r '.mattermost_dm[]? | if startswith("@") then . else "@" + . end' "$R")

        # A channel, by contrast, must NOT be @-prefixed - hence the separate
        # field rather than one list with a convention to remember.
        ch=$(jq -r '.mattermost_channel // ""' "$R")
        if [ -n "$ch" ]; then targets+=("${ch#@}"); fi

        if [ "${#targets[@]}" -eq 0 ]; then
          echo "FATAL: mattermost_dm is empty in $R - nobody would be messaged."
          echo "Add each developer's Mattermost @username there."
          exit 1
        fi

        ok=0; bad=0
        for t in "${targets[@]}"; do
          # jq builds the JSON, so a commit subject containing a quote,
          # backslash or newline cannot produce a malformed payload.
          payload=$(jq -n --arg ch "$t" --arg txt "$NOTIFY_MSG" '{channel:$ch, text:$txt}')
          # -L with --post301/--post302: Mattermost builds webhook URLs from its
          # configured Site URL, which is not necessarily the address reachable
          # from this host, so the URL it hands out may redirect. Plain curl
          # downgrades a followed POST to a GET, and Mattermost rejects GET on a
          # webhook - so without this the DM silently never arrives while the
          # build still looks fine.
          if curl -fsS -L --post301 --post302 --max-time 15 \
               -X POST -H 'Content-Type: application/json' \
               --data-binary "$payload" "$MM_HOOK" >/dev/null; then
            ok=$((ok + 1))
          else
            bad=$((bad + 1))
            echo "  DM to $t FAILED"
          fi
        done
        echo "Mattermost: $ok delivered, $bad failed, of ${#targets[@]}"
        [ "$bad" -eq 0 ]
      '''
    }
  }
}

def notifyEmail(String outcome, String msg) {
  def to = sh(returnStdout: true, script: '''#!/bin/bash
    set -euo pipefail
    jq -r '.email_to | join(",")' /home/rndadmin/deploy-config/notify-recipients.json
  ''').trim()

  // An empty list would mean a pipeline that reports success while telling
  // nobody - the same class of bug as a deploy that reports success while
  // deploying nothing. Refuse instead of pretending.
  if (!to) {
    error "email_to is empty in notify-recipients.json - refusing to 'send' to nobody"
  }

  def subject = (outcome == 'ok')
    ? '[prornd] testing-backend updated on Testing - rebase your branch'
    : '[prornd] testing-backend deploy FAILED on Testing - do not pull'

  mail to: to, subject: subject, body: msg
  echo "email sent to: ${to}"
}


pipeline {
  // The checkout must land in the live bench app directory — that is what
  // Frappe actually serves. With a plain `agent any`, Jenkins would check out
  // into /var/lib/jenkins/workspace/... and the migrate/restart below would run
  // against unchanged code: a deploy that reports success while deploying
  // nothing. (customWorkspace is the Pipeline equivalent of a freestyle job's
  // "Custom workspace" field — it cannot be set from the job config UI here.)
  agent {
    node {
      label ''
      customWorkspace '/home/rndadmin/frappe-dev/prornd/apps/rndopsapp'
    }
  }

  triggers { pollSCM('H/3 * * * *') }

  options {
    timestamps()
    disableConcurrentBuilds()
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }

  environment {
    BENCH      = '/home/rndadmin/.local/bin/bench'
    BENCH_DIR  = '/home/rndadmin/frappe-dev/prornd'
    SITE       = 'prornd.local'
    BASE_URL   = 'http://127.0.0.1:8000'
  }

  stages {
    // bench migrate takes its own backup before applying schema changes.
    stage('Migrate') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          cd "$BENCH_DIR"
          "$BENCH" --site "$SITE" migrate
        '''
      }
    }

    stage('Clear cache') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          cd "$BENCH_DIR"
          "$BENCH" --site "$SITE" clear-cache
        '''
      }
    }

    // The gunicorn web process auto-reloads on .py changes, but the worker,
    // scheduler and kafka_consumer processes do NOT — they need a real restart
    // to pick up new code.
    //
    // Bench runs as the frappe-bench user unit, not in a tmux session: tmux did
    // not survive a reboot, so Jenkins would come back and keep reporting
    // successful deploys to a server that was down.
    stage('Restart bench') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail

          # Jenkins is a SYSTEM service running as rndadmin, so it inherits no
          # XDG_RUNTIME_DIR and `systemctl --user` cannot find the user bus
          # without it. /run/user/1000 persists with no login only because
          # lingering is enabled for rndadmin (loginctl enable-linger).
          export XDG_RUNTIME_DIR=/run/user/$(id -u)

          if ! systemctl --user cat frappe-bench.service >/dev/null 2>&1; then
            echo "FATAL: frappe-bench.service not found for user $(whoami)."
            echo "Expected at ~/.config/systemd/user/frappe-bench.service"
            exit 1
          fi

          systemctl --user restart frappe-bench
          systemctl --user --no-pager is-active frappe-bench || true
        '''
      }
    }

    // Poll instead of a fixed sleep: restart time varies, and a too-short sleep
    // turns a healthy deploy into a false failure (or hides a real one).
    stage('Wait for bench') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          for i in $(seq 1 45); do
            if curl -fsS "$BASE_URL/api/method/ping" 2>/dev/null | grep -q pong; then
              echo "OK: bench responded after $((i * 2))s"
              exit 0
            fi
            sleep 2
          done
          echo "FATAL: bench did not answer /api/method/ping within 90s"
          echo "Logs: journalctl --user -u frappe-bench -n 50 --no-pager"
          exit 1
        '''
      }
    }

    stage('Smoke test') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail

          ping=$(curl -fsS "$BASE_URL/api/method/ping")
          printf '%s' "$ping" | grep -q pong || { echo "FATAL: ping returned: $ping"; exit 1; }

          # /app must redirect (301) rather than 500 — catches a site that boots
          # the web process but fails on app/doctype import.
          app=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/app")
          case "$app" in
            2*|3*) ;;
            *) echo "FATAL: /app returned HTTP $app"; exit 1 ;;
          esac

          echo "OK: ping=pong, /app=$app"
        '''
      }
    }
  }

  post {
    success {
      echo "Deployed testing-backend to 172.17.1.46"
      script { notifyAll('ok') }
    }
    failure {
      echo "Deploy FAILED. The site may be mid-restart or down."
      echo "Check: journalctl --user -u frappe-bench -n 50 --no-pager  /  tail -50 ${env.BENCH_DIR}/logs/web.error.log"
      script { notifyAll('fail') }
    }
  }
}
