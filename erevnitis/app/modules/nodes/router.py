"""
Nodes router - CRUD + загрузка конфигурационных файлов
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import os, shutil

from app.core.database import get_db
from app.core.security import require_admin, require_sre_or_admin, require_any_auth
from app.modules.nodes.models import Node
from app.modules.nodes.schemas import NodeCreate, NodeUpdate, NodeResponse

router = APIRouter()

# Папка для хранения конфигов (создаётся автоматически)
CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "configs")
os.makedirs(CONFIGS_DIR, exist_ok=True)


@router.get("/", response_model=list[NodeResponse])
def list_nodes(
    status: Optional[bool] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    query = db.query(Node)
    if status is not None:
        query = query.filter(Node.status == status)
    if tag:
        query = query.filter(Node.tags.contains(tag))
    return query.all()


@router.get("/stats/summary")
def nodes_summary(db: Session = Depends(get_db), _=Depends(require_any_auth)):
    total   = db.query(Node).count()
    online  = db.query(Node).filter(Node.status == True).count()
    offline = db.query(Node).filter(Node.status == False).count()
    return {"total": total, "online": online, "offline": offline}


@router.get("/{node_id}", response_model=NodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db), _=Depends(require_any_auth)):
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
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")

    # Удаляем файл конфига если есть
    if node.config_path and os.path.exists(node.config_path):
        os.remove(node.config_path)

    db.delete(node)
    db.commit()


# ══════════════════════════════════════════════════════════════
# ЗАГРУЗКА КОНФИГУРАЦИОННОГО ФАЙЛА
# ══════════════════════════════════════════════════════════════

@router.post("/{node_id}/config", status_code=200)
async def upload_config(
    node_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)   # sre и admin могут загружать
):
    """
    Загрузка конфигурационного файла для сервера.
    Принимает любой текстовый файл: .conf, .yml, .yaml, .json, .ini, .toml
    Сохраняет в папку configs/ и записывает путь в поле config_path узла.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")

    # Проверяем расширение файла
    allowed_extensions = {".conf", ".yml", ".yaml", ".json", ".ini", ".toml", ".cfg", ".txt"}
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешены: {', '.join(allowed_extensions)}"
        )

    # Сохраняем файл: configs/node_6_nginx.conf
    save_filename = f"node_{node_id}_{file.filename}"
    save_path = os.path.join(CONFIGS_DIR, save_filename)

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Обновляем путь в БД
    node.config_path = save_path
    db.commit()

    return {
        "message": f"Конфиг успешно загружен для {node.hostname}",
        "filename": file.filename,
        "saved_as": save_filename,
        "config_path": save_path
    }


@router.get("/{node_id}/config/download")
def download_config(
    node_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)   # все авторизованные могут скачать
):
    """
    Скачать конфигурационный файл сервера.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    if not node.config_path or not os.path.exists(node.config_path):
        raise HTTPException(status_code=404, detail="Конфигурационный файл не найден")

    filename = os.path.basename(node.config_path)
    return FileResponse(
        path=node.config_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.delete("/{node_id}/config", status_code=200)
def delete_config(
    node_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """
    Удалить конфигурационный файл сервера.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    if not node.config_path or not os.path.exists(node.config_path):
        raise HTTPException(status_code=404, detail="Конфигурационный файл не найден")

    os.remove(node.config_path)
    node.config_path = None
    db.commit()

    return {"message": "Конфигурационный файл удалён"}