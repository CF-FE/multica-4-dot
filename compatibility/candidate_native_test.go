// This file is copied into server/cmd/server in a temporary upstream checkout.
// It uses upstream TestMain's real router, in-process HTTP server and PG17 fixture.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"testing"
)

func candidateJSON(t *testing.T, method, path string, body any, want int, dst any) {
	t.Helper()
	resp := authRequest(t, method, path, body)
	if resp.StatusCode != want {
		resp.Body.Close()
		t.Fatalf("%s %s status %d, want %d", method, path, resp.StatusCode, want)
	}
	readJSON(t, resp, dst)
}

type candidateObject struct {
	ID          string `json:"id"`
	WorkspaceID string `json:"workspace_id"`
	ProjectID   string `json:"project_id"`
	Status      string `json:"status"`
}

type candidateRun struct {
	candidateObject
	IssueID          string          `json:"issue_id"`
	AgentID          string          `json:"agent_id"`
	TriggerCommentID string          `json:"trigger_comment_id"`
	CompletedAt      json.RawMessage `json:"completed_at"`
}

type candidateComment struct {
	ID              string            `json:"id"`
	IssueID         string            `json:"issue_id"`
	Content         string            `json:"content"`
	Supplements     []json.RawMessage `json:"supplements"`
	TriggerOutcomes []struct {
		TargetType string `json:"target_type"`
		TargetID   string `json:"target_id"`
		Status     string `json:"status"`
	} `json:"trigger_outcomes"`
}

func candidateProjectIssue(t *testing.T) (projectID, issueID string) {
	t.Helper()
	var project, issue candidateObject
	candidateJSON(t, "POST", "/api/projects?workspace_id="+testWorkspaceID,
		map[string]string{"title": t.Name()}, 201, &project)
	if project.ID == "" || project.WorkspaceID != testWorkspaceID {
		t.Fatal("project create did not return the expected workspace and an ID")
	}
	candidateJSON(t, "POST", "/api/issues?workspace_id="+testWorkspaceID,
		map[string]string{"title": t.Name(), "status": "todo", "project_id": project.ID}, 201, &issue)
	if issue.ID == "" || issue.WorkspaceID != testWorkspaceID || issue.ProjectID != project.ID {
		t.Fatal("issue create did not return the expected workspace, project and ID")
	}
	return project.ID, issue.ID
}

func candidateRunPath(issueID string) string {
	return "/api/issues/" + issueID + "/task-runs?scope=issue&view=timeline"
}

func candidatePostComment(t *testing.T, issueID, content string) candidateComment {
	t.Helper()
	var comment candidateComment
	path := "/api/issues/" + issueID + "/comments"
	candidateJSON(t, "POST", path, map[string]string{"type": "comment", "content": content}, 201, &comment)
	if comment.ID == "" || comment.IssueID != issueID || comment.Content != content {
		t.Fatal("write receipt does not match the stored comment, content and Issue")
	}
	var comments []candidateComment
	candidateJSON(t, "GET", path, nil, 200, &comments)
	for _, stored := range comments {
		if stored.ID == comment.ID && stored.IssueID == issueID && stored.Content == content {
			return comment
		}
	}
	t.Fatal("comment missing from the Issue's native read-back")
	return comment
}

func TestCandidateIdentity(t *testing.T) {
	resp, err := http.Get(testServer.URL + "/api/me")
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 401 {
		t.Fatalf("unauthenticated identity got %d, want 401", resp.StatusCode)
	}
	var identity candidateObject
	candidateJSON(t, "GET", "/api/me", nil, 200, &identity)
	if identity.ID != testUserID {
		t.Fatal("authenticated identity does not match the fixture owner")
	}
}

func TestCandidateOwnership(t *testing.T) {
	projectID, issueID := candidateProjectIssue(t)
	var project, issue candidateObject
	candidateJSON(t, "GET", "/api/projects/"+projectID, nil, 200, &project)
	candidateJSON(t, "GET", "/api/issues/"+issueID, nil, 200, &issue)
	if project.ID != projectID || project.WorkspaceID != testWorkspaceID ||
		issue.ID != issueID || issue.WorkspaceID != testWorkspaceID || issue.ProjectID != projectID || issue.Status != "todo" {
		t.Fatal("read-back ownership or status does not match the fixture")
	}
	agentID := getAgentID(t)
	comment := candidatePostComment(t, issueID, fmt.Sprintf("[@FixtureAgent](mention://agent/%s) run", agentID))
	var runs []candidateRun
	candidateJSON(t, "GET", candidateRunPath(issueID), nil, 200, &runs)
	if len(runs) != 1 || runs[0].ID == "" || runs[0].IssueID != issueID ||
		runs[0].WorkspaceID != testWorkspaceID || runs[0].AgentID != agentID || runs[0].TriggerCommentID != comment.ID ||
		(runs[0].ProjectID != "" && runs[0].ProjectID != projectID) || len(runs[0].CompletedAt) == 0 {
		t.Fatal("native Run timeline does not match the Issue, workspace, comment and agent")
	}
}

func TestCandidateScopeDenial(t *testing.T) {
	projectID, issueID := candidateProjectIssue(t)
	ctx := context.Background()
	var outsider, otherWorkspace string
	const email = "isolated-outsider@example.test"
	if err := testPool.QueryRow(ctx, `INSERT INTO "user" (name, email) VALUES ('Outsider', $1) RETURNING id`, email).Scan(&outsider); err != nil {
		t.Fatal(err)
	}
	if err := testPool.QueryRow(ctx, `INSERT INTO workspace (name, slug, description) VALUES ('Other', 'candidate-other', '') RETURNING id`).Scan(&otherWorkspace); err != nil {
		t.Fatal(err)
	}
	if _, err := testPool.Exec(ctx, `INSERT INTO member (workspace_id, user_id, role) VALUES ($1, $2, 'owner')`, otherWorkspace, outsider); err != nil {
		t.Fatal(err)
	}
	token, err := generateTestJWT(outsider, email, "Outsider")
	if err != nil {
		t.Fatal(err)
	}
	fixtures := []struct{ method, path string }{
		{"GET", "/api/projects/" + projectID},
		{"GET", "/api/issues/" + issueID},
		{"GET", candidateRunPath(issueID)},
		{"POST", "/api/issues/" + issueID + "/comments"},
	}
	for _, fixture := range fixtures {
		var body io.Reader
		if fixture.method == "POST" {
			body = bytes.NewBufferString(`{"type":"comment","content":"denied fixture"}`)
		}
		req, err := http.NewRequest(fixture.method, testServer.URL+fixture.path, body)
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("X-Workspace-ID", otherWorkspace)
		req.Header.Set("Content-Type", "application/json")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != 403 && resp.StatusCode != 404 {
			t.Errorf("cross-workspace %s %s status %d, want 403 or 404", fixture.method, fixture.path, resp.StatusCode)
		}
	}
	var comments []candidateComment
	candidateJSON(t, "GET", "/api/issues/"+issueID+"/comments", nil, 200, &comments)
	if len(comments) != 0 || countPendingTasks(t, issueID) != 0 {
		t.Fatal("denied comment request stored data or produced an execution")
	}
}

func TestCandidateSilentComment(t *testing.T) {
	_, issueID := candidateProjectIssue(t)
	mention := fmt.Sprintf("[@FixtureAgent](mention://agent/%s)", getAgentID(t))
	comment := candidatePostComment(t, issueID, "/note "+mention+" fixture record")
	var runs []candidateRun
	candidateJSON(t, "GET", candidateRunPath(issueID), nil, 200, &runs)
	if len(comment.TriggerOutcomes) != 0 || len(comment.Supplements) != 0 || len(runs) != 0 || countPendingTasks(t, issueID) != 0 {
		t.Fatal("silent comment emitted a trigger, supplement or Run")
	}
}

func TestCandidateNormalComment(t *testing.T) {
	_, issueID := candidateProjectIssue(t)
	agentID := getAgentID(t)
	comment := candidatePostComment(t, issueID, fmt.Sprintf("[@FixtureAgent](mention://agent/%s) fixture record", agentID))
	if len(comment.TriggerOutcomes) != 1 || comment.TriggerOutcomes[0].TargetID != agentID ||
		comment.TriggerOutcomes[0].TargetType != "agent" || comment.TriggerOutcomes[0].Status != "queued" {
		t.Fatal("normal comment did not return one queued outcome for the fixture agent")
	}
	if countPendingTasks(t, issueID) != 1 || latestTriggerCommentID(t, issueID) != comment.ID {
		t.Fatal("normal comment did not produce one Run linked to its write receipt")
	}
	var runs []candidateRun
	candidateJSON(t, "GET", candidateRunPath(issueID), nil, 200, &runs)
	if len(runs) != 1 || runs[0].ID == "" || runs[0].IssueID != issueID || runs[0].TriggerCommentID != comment.ID {
		t.Fatal("normal comment's queued Run was not visible in the native timeline")
	}
	t.Log("persisted comment, queued receipt and native execution ID reconciled")
}
