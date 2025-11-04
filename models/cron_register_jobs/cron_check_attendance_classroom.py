# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, api, fields
from odoo.exceptions import UserError
import logging

from ....maya_core.support.maya_logger.exceptions import MayaException

# Moodle
from ....maya_core.support.maya_moodleteacher.maya_moodle_connection import MayaMoodleConnection
from ....maya_core.support.maya_moodleteacher.maya_moodle_user import MayaMoodleUsers

from ....maya_core.models.cron_register_jobs.cron_job_enrol_users import CronJobEnrolUsers
from ....maya_core.models.student import Student

from ....maya_core.support.helper import read_itaca_csv, add_error_code

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
    itaca_filename = self.env['ir.config_parameter'].get_param('maya_core.itaca_students_data')
    if not itaca_filename:
      print(f'\033[0;31m[ERROR]\033[0m No se ha definido el nombre del fichero de datos de itaca')
      return

    csv_file = '/mnt/odoo-repo/itaca/' + itaca_filename

    errors = []

    try:
      df, data_stack = read_itaca_csv(csv_file)
    except Exception as e:
      print(f"\033[0;31m[ERROR]\033[0m Error procesando el fichero csv: {str(e)}")
      return
    
    # creo un diccionario con los cursos
    course_dict = {
      c.code.strip(): c.id
      for c in self.env['maya_core.course'].search([])
      if c.code
    }

    for classroom in check_classrooms_id:
      try:
        print('\033[0;34m[INFO]\033[0m Obteniendo usuarios del aula -> moodle_id:', classroom[0])  
        
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
          try:
            error_code = ''
            
            # Crea el estudiante si no existe
            maya_user =  CronJobEnrolUsers.enrol_student(self, user[0], classroom[1], course_id, only_create=True) 

            # actualizo sus datos desde Itaca
            _, record_errors = Student.update_student_data_from_itaca(maya_user, df, data_stack, course_dict)

            # para evitar conflictos en aulas compartidas, solo sigo si el alumnno es del
            # ciclo que se está analizando
            if course_id not in maya_user.courses_ids.mapped('course_id').ids:
              continue
            else: # lo matriculamos
              maya_user =  CronJobEnrolUsers.enrol_student(self, user[0], classroom[1], course_id) 

            # Lo añado en lista de cancelaciones de oficio
            subject_student = self.env['maya_core.subject_student_rel']\
              .search([
                ('subject_id', '=', classroom[1]),('student_id', '=', maya_user.id),('course_id', '=', course_id)
                ], limit=1)
            
            # lo acabo de matricular luego debería haber un alumno
            # si no lo hay es que posiblemente el alumno esté matriculado en maya de ese 
            # módulo en otro ciclo.
            # Eso puede pasar si el alumno está en dos o más ciclos y comparten el aula.
            # NO es posible definir para ese módulo, en cual de los dos ciclos está matriculado
            if not subject_student:
              # busco sin tener en cuenta el curso
              subject_student = self.env['maya_core.subject_student_rel']\
                .search([
                  ('subject_id', '=', classroom[1]),('student_id', '=', maya_user.id)
                ], limit=1)
              
              error_code = 'A01'
            
            existing_cancellation = self.env['maya_students.cancellation'].search([
              ('subject_student_rel_id', '=', subject_student.id)
            ], limit=1)

            if existing_cancellation:   # YA EXISTE: actualizo las fechas
              existing_cancellation.write(
                { 'query_date': fields.Datetime.now(),
                  'lastaccess_date': user[1],
                  'classroom_moodle_id': classroom[0],
                  'error_codes': add_error_code(error_code or '', existing_cancellation.error_codes or '') 
                  })
              cancellation = existing_cancellation
            else:
              cancellation = self.env['maya_students.cancellation'].create([
                { 'subject_student_rel_id': subject_student.id,
                  'cancellation_type': 'OFC',
                  'query_date': fields.Datetime.now(),
                  'lastaccess_date': user[1],
                  'situation': '1',
                  'classroom_moodle_id': classroom[0] }])
              
            # si es nueva o sigue en riesgo lo añado al set
            processed_cancellation_ids.add(cancellation.id)
          except Exception as e:
            _logger.error(f"Error procesando el aula moodle_id:{classroom[0]}. Usuario {maya_user.student_info}. {str(e)}")
            errors.append(f'Error procesando el aula moodle_id:{classroom[0]}. Usuario {maya_user.student_info}. {str(e)} ')
            self.env.cr.rollback() # Deshacemos cualquier cambio de esta usuiario en este aula
            continue 

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
        _logger.error(f"Error procesando el aula moodle_id:{classroom[0]}: {str(e)}")
        errors.append(f'Error procesando el aula moodle_id:{classroom[0]}')
        self.env.cr.rollback() # Deshacemos cualquier cambio de esta aula
        continue 

    errors_filename = ''
    if len (errors)>0:
      date_str = datetime.now().strftime("%y%m%d%H%M")

      errors_filename = f"/var/log/odoo/errores_check_attendance_{date_str}.txt" 
      try:
        with open(errors_filename, 'w', encoding='utf-8') as f:
          for line in errors:
            f.write(f"{line}\n")
        
        # TODO lo utilizaremos en la notificacion via mail o telegram al adminstrador
        errors_filename = f'\r{len(errors)} error(es). Más información en: ' + errors_filename

      except IOError as e:
        raise UserError(f"Error al escribir en el fichero: {str(e)}")

  
              