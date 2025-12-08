# -*- coding: utf-8 -*-
import logging
from datetime import datetime, date

from typing import Tuple

from ...maya_core.support.maya_logger.exceptions import MayaException

_logger = logging.getLogger(__name__)

    
def create_info_register_cancellation(current_employee, type: str, previous_register: str) -> Tuple[str, str, date]:
  """
  Crear la información a almacenar en el registro y modifica el comentario y
  situation en función del tipo de acción tomada

  current_employee: self.env.user.maya_employee_id
  type: nueva situacion
  previous_register: comentarios previos
  """

  assert type == 'AV' or type == 'R2M' or type == 'JUS' or type == 'R2QC', f'Tipo de acción en anulación de oficio no soportada'
    
  current_datetime = datetime.now()
  current_day = current_datetime.strftime('%d-%m-%Y %H:%M:%S')

  if type =='AV':
    msg_info = 'Ha notificado la decisión de anular el módulo'
    sit = '6'
  elif type =='R2M':
    msg_info = 'No se ha podido contactar telefonicamente. Se envía mail de notificación R2'
    sit = '5'
  elif type =='JUS':
    msg_info = 'Justificación aceptada'
    sit = '7'
  elif type == 'R2QC':
    msg_info = 'Notifica que quiere continuar. Debe conectarse al aula o será dado de baja'
    sit = '5'


  info = f'({current_day}) [{type}] {msg_info}. @{current_employee.display_name or "--"} | #{current_employee.phone_extension or "--"}]' 

  comments = ((previous_register or '') + '\n' + info).lstrip('\n')

  return comments, sit, current_datetime.date()