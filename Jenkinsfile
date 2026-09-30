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
    // NOT named TMUX: that is tmux's own reserved variable (it expects
    // <socket-path>,<pid>,<idx> and uses it to detect nesting). Setting
    // TMUX='frappe' made tmux treat 'frappe' as a socket path and fail with
    // "error connecting to frappe" — which looked exactly like a missing session.
    TMUX_SESSION = 'frappe'
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
    // to pick up new code. This is BENCH_RUNBOOK.md's documented full-restart
    // procedure, driven through the tmux session honcho runs in.
    stage('Restart bench') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail

          if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
            echo "FATAL: tmux session '$TMUX_SESSION' not found."
            echo "Bench is expected to run inside it (see BENCH_RUNBOOK.md)."
            echo "Check: tmux ls   (socket lives at /tmp/tmux-\$(id -u)/default)"
            exit 1
          fi

          tmux send-keys -t "$TMUX_SESSION" C-c
          sleep 3
          tmux send-keys -t "$TMUX_SESSION" "cd $BENCH_DIR && bench start" Enter
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
          echo "Attach with: tmux attach -t $TMUX_SESSION"
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
    success { echo "Deployed testing-backend to 172.17.1.46" }
    failure {
      echo "Deploy FAILED. The site may be mid-restart or down."
      echo "Check: tmux attach -t frappe   /   tail -50 ${BENCH_DIR}/logs/web.error.log"
    }
  }
}
