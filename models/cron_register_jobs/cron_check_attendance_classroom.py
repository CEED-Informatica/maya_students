# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, api, fields
import logging

from ....maya_core.support.maya_logger.exceptions import MayaException

# Moodle
from ....maya_core.support.maya_moodleteacher.maya_moodle_connection import MayaMoodleConnection
from ....maya_core.support.maya_moodleteacher.maya_moodle_user import MayaMoodleUsers

from ....maya_core.models.cron_register_jobs.cron_job_enrol_users import CronJobEnrolUsers
from ....maya_core.models.student import Student

from ....maya_core.support.helper import read_itaca_csv

_logger = logging.getLogger(__name__)

class CronCheckAttendanceClassroom(models.TransientModel):
  _name = 'maya_students.cron_check_attendance_classroom'

  @api.model
  def cron_check_attendance_classroom(self, check_classrooms_id: list[tuple[int,int]], course_id: int):

    # ŧODO ponerlo en configuraciones
    set_midnight = True
    days = 8

    # comprobaciones iniciales
    if check_classrooms_id == None:
      _logger.error("CRON: check_classrooms_id no definido")
      return
    
    print(f'\033[0;34m[INFO]\033[0m Comprobando asistencia en el ciclo {course_id}. Número de aulas: {len(check_classrooms_id)}')

    current_sy = (self.env['maya_core.school_year'].search([('state', '=', 1)])) # curso escolar actual  

    try:
      conn = MayaMoodleConnection( 
        user = self.env['ir.config_parameter'].get_param('maya_core.moodle_user_admin'), 
        moodle_host = self.env['ir.config_parameter'].get_param('maya_core.moodle_url')) 
    except Exception as e:
      raise Exception('No es posible realizar la conexión con Moodle' + str(e))
    

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

    print(f'\033[0;34m[INFO]\033[0m Fecha actual: {current_day}')

    if set_midnight:
      # Calculo la fecha límite: medianoche de N días antes
      deadline = current_datetime.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    else:
      deadline = current_datetime - timedelta(days=days)

    #TODO parametrizar estos datos en configuraciones
    archivo_csv = '/mnt/odoo-repo/itaca/temp.csv'

    df, data_stack= read_itaca_csv(archivo_csv)

    for classroom in check_classrooms_id:
      try:
        print('\033[0;34m[INFO]\033[0m Obteniendo usuarios del aula ->', classroom[1])  
        
        # obtención de los usuarios 
        users = MayaMoodleUsers.from_course(conn,  classroom[0], only_students = True)
        risk_users = []

        for user in users:
          lastcourseaccess = getattr(user, "lastcourseaccess", None)

          if not lastcourseaccess or lastcourseaccess == 0:
            access_datetime =  datetime(2000, 1, 1, 0, 0) # con datetime.min, el widget no lo mostraba correctamente
          else:
            access_datetime = datetime.fromtimestamp(int(lastcourseaccess))
          
          if access_datetime < deadline:
            risk_users.append([user, access_datetime])


        # Preparo los datos para poder eliminar las anulaciones de los alumnos que ya se han
        # conectado
        # Estudiantes del módulo y ciclo
        all_rels_in_classroom = self.env['maya_core.subject_student_rel'].search([
            ('subject_id', '=', classroom[1]),
            ('course_id', '=', course_id)
        ])

        # Anulaciones de oficio existentes para esta aula
        existing_cancellations_in_db = self.env['maya_students.cancellation'].search([
            ('subject_student_rel_id', 'in', all_rels_in_classroom.ids),
            ('cancellation_type', '=', 'OFC') 
        ])
        
        # Creo un set (resta más rápido) con todos los que hay
        existing_cancellation_ids = set(existing_cancellations_in_db.ids)
        
        # otro para los que estén en riesgo
        processed_cancellation_ids = set()

        for user in risk_users:
          # los matriculamos en Maya si no lo están
          maya_user =  CronJobEnrolUsers.enrol_student(self, user[0], classroom[1], course_id) 

          # actualizo sus datos desde Itaca
          _, record_errors = Student.update_student_data_from_itaca(maya_user, df, data_stack)

          # Lo añado en lista de cancelaciones de oficio
          subject_student = self.env['maya_core.subject_student_rel']\
            .search([
              ('subject_id', '=', classroom[1]),('student_id', '=', maya_user.id),('course_id', '=', course_id)
              ], limit=1)
          
          # lo acabo de matricular luego tiene que devolverme 1 alumno
          
          existing_cancellation = self.env['maya_students.cancellation'].search([
            ('subject_student_rel_id', '=', subject_student.id)
          ], limit=1)

          if existing_cancellation:   # YA EXISTE: actualizo las fechas
            existing_cancellation.write(
              { 'query_date': fields.Datetime.now(),
                'lastaccess_date': user[1] })
            cancellation = existing_cancellation
          else:
            cancellation = self.env['maya_students.cancellation'].create([
              { 'subject_student_rel_id': subject_student.id,
                'cancellation_type': 'OFC',
                'query_date': fields.Datetime.now(),
                'lastaccess_date': user[1],
                'situation': '1' }])
            
          # si es nueva o sigue en riesgo lo añado al set
          processed_cancellation_ids.add(cancellation.id)

        # obtengo las obsoletas, gente que sí se ha conectado
        deprecated_cancellation_ids = existing_cancellation_ids - processed_cancellation_ids

        if deprecated_cancellation_ids:
          _logger.info(f"Aula {classroom[1]}: {len(deprecated_cancellation_ids)} anulaciones obsoletas encontradas.")
          
          cancellations_to_delete = self.env['maya_students.cancellation'].search([
              ('id', 'in', list(deprecated_cancellation_ids)),
              ('situation', 'not in', ['5']) # si esta justificada no se borra
          ])

          if cancellations_to_delete:
            count = len(cancellations_to_delete)
            cancellations_to_delete.unlink() # Borramos los registros
            _logger.info(f"Aula {classroom[1]}: {count} cancelaciones obsoletas borradas.")    

        self.env.cr.commit()  ## fuerzo el commit a la base de datos UNA VEZ por aula

      except Exception as e:
        _logger.error(f"Error procesando el {classroom[1]}: {str(e)}")
        self.env.cr.rollback() # Deshacemos cualquier cambio de esta aula
        continue 

        
              