/*
    Pipeline script for Jira blocker resolution time report
*/

pipeline {
    agent {
        label "agents"
    }

    environment {
        QE_DASHBOARD_SHEET = "IBMCEPH JIRA QE - 9.2 Quality Dashboard"
    }

    stages {
        stage('Prepare Node') {
            steps {
                cleanWs()
                checkout(
                    scm: [
                        $class: 'GitSCM',
                        branches: [[name: 'main']],
                        extensions: [[
                            $class: 'CleanBeforeCheckout',
                            deleteUntrackedNestedRepositories: true
                        ], [
                            $class: 'WipeWorkspace'
                        ], [
                            $class: 'CloneOption',
                            depth: 1,
                            noTags: true,
                            shallow: true,
                            timeout: 10,
                            reference: ''
                        ]],
                        userRemoteConfigs: [[
                            url: 'https://github.com/ibmstorage/ceph-qe-jira-reporter.git'
                        ]]
                    ],
                    changelog: false,
                    poll: false
                )
            }
        }

        stage('Setup Environment') {
            steps {
                sh '''
                    rm -rf .venv
                    python3 -m venv .venv
                    .venv/bin/python3 -m pip install --upgrade pip
                    .venv/bin/python3 -m pip install -r requirements.txt
                '''
            }
        }

        stage('Execute Workflow') {
            steps {
                withCredentials([
                    string(credentialsId: 'atlassian-jira-token', variable: 'JIRA_TOKEN'),
                    file(credentialsId: 'gcp-service-account', variable: 'GCP_SERVICE_ACCOUNT')
                ]) {
                    withEnv(["GSPREAD_SERVICE_ACCOUNT=${env.GCP_SERVICE_ACCOUNT}"]) {
                        sh "JIRA_TOKEN='${JIRA_TOKEN}' .venv/bin/python3 scripts/blocker_resolution_time.py '${QE_DASHBOARD_SHEET}'"
                    }
                }
            }
        }
    }
}
