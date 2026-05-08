"""
Nodes router - CRUD for server assets
RBAC: GET - any auth, POST/PATCH - sre+admin, DELETE - admin only
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.security import require_admin, require_sre_or_admin, require_any_auth
from app.modules.nodes.models import Node
from app.modules.nodes.schemas import NodeCreate, NodeUpdate, NodeResponse

router = APIRouter()


@router.get("/", response_model=list[NodeResponse])
def list_nodes(
    status: Optional[bool] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    """List all nodes with optional filters. All authenticated users."""
    query = db.query(Node)
    if status is not None:
        query = query.filter(Node.status == status)
    if tag:
        query = query.filter(Node.tags.contains(tag))
    return query.all()


@router.get("/{node_id}", response_model=NodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db), _=Depends(require_any_auth)):
    """Get single node by ID"""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return node


@router.post("/", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(
    node_data: NodeCreate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """Create new node. SRE and Admin only."""
    if db.query(Node).filter(Node.ip_address == node_data.ip_address).first():
        raise HTTPException(status_code=400, detail="Узел с таким IP уже существует")
    if db.query(Node).filter(Node.hostname == node_data.hostname).first():
        raise HTTPException(status_code=400, detail="Узел с таким hostname уже существует")

    node = Node(**node_data.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.patch("/{node_id}", response_model=NodeResponse)
def update_node(
    node_id: int,
    node_data: NodeUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """Update node fields. SRE and Admin only."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")

    update_data = node_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(node, key, value)
    node.last_seen = datetime.utcnow()

    db.commit()
    db.refresh(node)
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    """Delete node. Admin only."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    db.delete(node)
    db.commit()


@router.get("/stats/summary")
def nodes_summary(db: Session = Depends(get_db), _=Depends(require_any_auth)):
    """Summary statistics for dashboard"""
    total = db.query(Node).count()
    online = db.query(Node).filter(Node.status == True).count()
    offline = db.query(Node).filter(Node.status == False).count()
    return {"total": total, "online": online, "offline": offline}
