from __future__ import annotations

import argparse
import re
import urllib.parse
from typing import Any

from agent.web import panel_server as base


_SAFE_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")


def _enhance_panel_html(html: str) -> str:
    badge_marker = (
        ".badge.failed,.badge.blocked,.badge.cancelled"
        "{background:rgba(255,107,122,.14);color:#ff8d99}"
    )
    badge_replacement = (
        ".badge.awaiting_approval{background:rgba(242,184,75,.16);color:#ffd378}"
        + badge_marker
        + ".approval-actions{display:none;align-items:center;gap:12px;"
        "padding:14px;margin:0 0 12px;border:1px solid var(--line);"
        "border-radius:12px;background:#101a2d}"
        ".approval-actions.show{display:flex;flex-wrap:wrap}"
        ".approval-copy{flex:1;min-width:240px;color:#ffd378;font-size:13px}"
        ".btn.approve{background:var(--ok);color:#07140f}"
    )
    if badge_marker not in html:
        raise RuntimeError("panel_badge_marker_missing")
    html = html.replace(badge_marker, badge_replacement, 1)

    detail_marker = (
        '<section class="card history" id="details"><h2>Selected request</h2>'
        '<div id="detailTitle" class="muted" style="margin-bottom:10px">'
        'Select a request from the table.</div><div class="detail" id="detailBox">'
        'No request selected.</div></section>'
    )
    detail_replacement = (
        '<section class="card history" id="details"><h2>Selected request</h2>'
        '<div id="detailTitle" class="muted" style="margin-bottom:10px">'
        'Select a request from the table.</div>'
        '<div id="approvalActions" class="approval-actions">'
        '<div class="approval-copy">This mission is waiting for your manual approval. '
        'Approval validates the persisted mission branch and performs a controlled '
        'fast-forward merge to main.</div>'
        '<button class="btn approve" id="approveBtn">Approve &amp; Merge</button>'
        '</div>'
        '<div class="detail" id="detailBox">No request selected.</div></section>'
    )
    if detail_marker not in html:
        raise RuntimeError("panel_detail_marker_missing")
    html = html.replace(detail_marker, detail_replacement, 1)

    load_marker = (
        "if(['failed','blocked','cancelled'].includes(s))problem++;"
    )
    if load_marker not in html:
        raise RuntimeError("panel_problem_counter_marker_missing")
    html = html.replace(
        load_marker,
        "if(['failed','blocked','cancelled','awaiting_approval'].includes(s))problem++;",
        1,
    )

    select_marker = (
        "async function selectRequest(id){try{const j=await api('/api/requests/'"
        "+encodeURIComponent(id)+'/status');document.getElementById('detailTitle')"
        ".innerHTML=`<strong>${escapeHtml(id)}</strong> ${badge(j.data?.status||j.status||'unknown')}`;"
        "document.getElementById('detailBox').textContent=JSON.stringify(j.data||j,null,2)}"
        "catch(e){toast(e.message)}}"
    )
    if select_marker not in html:
        raise RuntimeError("panel_select_request_marker_missing")

    select_replacement = r'''let selectedRequestId=null;
let selectedApprovalMissionId=null;
async function selectRequest(id){
  try{
    const j=await api('/api/requests/'+encodeURIComponent(id)+'/status');
    const data=j.data||j;
    selectedRequestId=id;
    document.getElementById('detailTitle').innerHTML=`<strong>${escapeHtml(id)}</strong> ${badge(data.status||'unknown')}`;
    document.getElementById('detailBox').textContent=JSON.stringify(data,null,2);
    const actions=document.getElementById('approvalActions');
    const mission=data.missions?.[0]?.mission||{};
    selectedApprovalMissionId=null;
    if(data.status==='awaiting_approval' && mission.id && mission.requires_action==='manual_review'){
      selectedApprovalMissionId=mission.id;
      actions.classList.add('show');
    }else{
      actions.classList.remove('show');
    }
  }catch(e){toast(e.message)}
}
async function approveSelectedMission(){
  const missionId=selectedApprovalMissionId;
  if(!missionId){toast('No mission is awaiting approval.');return}
  if(!confirm('Approve this reviewed mission and fast-forward its verified branch into main?'))return;
  const btn=document.getElementById('approveBtn');
  btn.disabled=true;
  btn.textContent='Approving…';
  try{
    await api('/api/missions/'+encodeURIComponent(missionId)+'/approve',{method:'POST',body:'{}'});
    toast('Mission approved and merge completed.');
    await loadRequests();
    if(selectedRequestId)await selectRequest(selectedRequestId);
  }catch(e){
    toast('Approval blocked: '+e.message);
  }finally{
    btn.disabled=false;
    btn.textContent='Approve & Merge';
  }
}
document.getElementById('approveBtn').onclick=approveSelectedMission;'''
    html = html.replace(select_marker, select_replacement, 1)
    return html


base.PANEL_HTML = _enhance_panel_html(base.PANEL_HTML)


class ApprovalPanelServer(base.PanelServer):
    """Panel adapter exposing only the bounded Core manual-approval action."""

    def handler(self):
        parent = super().handler()
        outer = self

        class Handler(parent):
            def do_POST(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                parts = [
                    urllib.parse.unquote(part)
                    for part in parsed.path.split("/")
                    if part
                ]
                if (
                    len(parts) == 4
                    and parts[0] == "api"
                    and parts[1] == "missions"
                    and parts[3] == "approve"
                ):
                    if not self._require_auth():
                        return
                    mission_id = parts[2]
                    if not _SAFE_MISSION_ID.fullmatch(mission_id):
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": {
                                    "code": "invalid_mission_id",
                                    "message": "Invalid mission id",
                                },
                            },
                        )
                        return
                    self._proxy(
                        "/v1/execution-outcomes",
                        method="POST",
                        payload={
                            "action": "approve_manual_review",
                            "mission_id": mission_id,
                            "approved_by": outer.config.username,
                        },
                    )
                    return
                super().do_POST()

        return Handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MITIGATE AI web control panel with governed approval"
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = base.build_config_from_env()
    if args.host or args.port:
        cfg = base.PanelConfig(
            host=args.host or cfg.host,
            port=args.port or cfg.port,
            runtime_base_url=cfg.runtime_base_url,
            project_id=cfg.project_id,
            username=cfg.username,
            password=cfg.password,
            api_token=cfg.api_token,
        )
    cfg.validate()
    ApprovalPanelServer(cfg).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
