# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, api
import logging

from ....maya_core.support.maya_logger.exceptions import MayaException

# Moodle
from ....maya_core.support.maya_moodleteacher.maya_moodle_connection import MayaMoodleConnection
from ....maya_core.support.maya_moodleteacher.maya_moodle_user import MayaMoodleUsers


_logger = logging.getLogger(__name__)

class CronCheckAttendanceClassroom(models.TransientModel):
  _name = 'maya_students.cron_check_attendance_classroom'

  @api.model
  def cron_check_attendance_classroom(self, check_classrooms_id: list[tuple[int,str]], course_id: int):

    # ŧODO ponerlo en configuraciones
    set_midnight = True
    days = 8

    # comprobaciones iniciales
    if check_classrooms_id == None:
      _logger.error("CRON: check_classrooms_id no definido")
      return
    
    _logger.info(f"Comprobando asistencia en el ciclo {course_id}. Número de aulas: {len(check_classrooms_id)}")

    current_sy = (self.env['maya_core.school_year'].search([('state', '=', 1)])) # curso escolar actual  

    try:
      conn = MayaMoodleConnection( 
        user = self.env['ir.config_parameter'].get_param('maya_core.moodle_user'), 
        moodle_host = self.env['ir.config_parameter'].get_param('maya_core.moodle_url')) 
    except Exception as e:
      raise Exception('No es posible realizar la conexión con Moodle' + e)
    

    if len(current_sy) == 0:
      raise MayaException(
          _logger, 
          'No se ha definido un curso actual',
          50, # critical
          comments = '''Es posible que no se haya marcado como actual ningún curso escolar''')
    else:
      current_school_year = current_sy[0]

    current_datetime = datetime.now()
    current_day = current_datetime.strftime('%d-%m-%Y %H:%M:%S')

    _logger.info(f'Fecha actual:', current_day) 

    for classroom in check_classrooms_id:
      print('\033[0;34m[INFO]\033[0m Obteniendo usuarios del aula ->', classroom[1])  
      
      # obtención de los usuarios 
      users = MayaMoodleUsers.from_course(conn,  classroom[0], only_students = True)

      risk_users = 0
      if set_midnight:
        # Calculo la fecha límite: medianoche de N días antes
        deadline = current_datetime.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
      else:
        deadline = current_datetime - timedelta(days=days)
