#!/usr/bin/python

import web
from jenkins import Jenkins

import json, urllib2, re
from datetime import datetime

from buildutil import *
import BuildConfig
import ODDeploy
import CIDeploy
import Nomad
import appconfig

render = web.template.render('template/', base='layout')
urls = (
  '/', 'Index',
  '/add', 'Add',
  '/build', 'Build',
  '/getbuild', 'GetBuild',
  '/updatebuild', 'UpdateBuild',
  '/remove', 'Remove',
  '/sendmail', 'SendMailToAdmin',
  '/cron', 'BuildCron',
  '/fullview', 'FullView',
  '/logger', 'Logger',
  '/buildconfig', BuildConfig.app_BuildConfig,
  '/ODDeploy', ODDeploy.app_ODDeploy,
  '/CIDeploy', CIDeploy.app_CIDeploy,
  '/Nomad', Nomad.app_Nomad,
)

web.config.smtp_server = 'localhost'
web.config.smtp_port = 25
web.config.debug = True
app = web.application(urls, globals())


db = web.database(dbn='sqlite', db='branchBuilder')

class Index:
  def GET(self):
    #self.update_status()
    #builds = db.select('builds', order="last_build_date DESC", where="repos is not null")
    builds = db.query("select a.task_id, a.author, a.branch, a.repos, a.version, a.author, \
      a.styleguide_repo, a.styleguide_branch, a.sidecar_repo, a.sidecar_branch, a.last_build_date, \
      ifnull(b.status, a.status) as status \
      from builds as a \
      left join  builds_status as b \
      on a.task_id=b.task_id \
      order by b.status desc,a.last_build_date desc")

    return render.index(builds, appconfig.site_url)

  def update_status(self):
    builds_status = db.select('builds_status')

    for build_status in builds_status:
      db.update('builds', where="task_id=" + str(build_status.task_id), status=build_status.status)

  def get_job_name(self, string):
    buildUtil = BuildUtil()
    return buildUtil.get_job_name(repos=string)
      
class Add:
  def POST(self):
    i = web.input()

    #TODO
    #check duplicate
    #if found duplicate then build
    isDuplicate = False
    if isDuplicate:
      pass
    #else add a new build
    else:
      if (hasattr(i, 'upgrade_package')):
        upgrade_package = i.upgrade_package 
      else:
        upgrade_package = 0

      buildUtil = BuildUtil()
      i = buildUtil.sanitize_input(i)
      styleguide_branch = buildUtil.determine_styleguide_branch(i.styleguide_repo, i.styleguide_branch, i.version)
      n = db.insert('builds',  repos=i.repos, branch=i.branch, version=i.version, author=i.author,
            styleguide_repo=i.styleguide_repo, styleguide_branch=styleguide_branch, sidecar_repo=i.sidecar_repo,
            sidecar_branch=i.sidecar_branch,
            last_build_number=1000,
            last_build_date="",
            start_time="",
            status="Available",
            package_list="ent",
            upgrade_package = upgrade_package)

      date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      f = open("logger", "a")
      f.write(date_now + " [Add Action:]," + i.repos + "," + i.branch + "," + i.version + "," + i.author + "," + i.styleguide_repo + "," + i.styleguide_branch + "," + i.sidecar_repo + "," + i.sidecar_branch + ", ent, Available" + str(upgrade_package) + "\n")
      f.close()
      raise web.seeother('/')

class Remove:
  def GET(self):
    i = web.input()
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    f = open("logger", "a")
    for m in db.select('builds', where="task_id =" +  i.task_id):
      f.write(date_now + " [Delete Action:]" + str(m.task_id) + "," + m.repos + "," + m.branch + "," + m.version + "," + m.author + "," + m.styleguide_repo + "," + m.styleguide_branch + "," + m.sidecar_repo + "," + m.sidecar_branch + "," + m.package_list + "\n")
    f.close()

    n = db.delete('builds', where="task_id =" +  i.task_id)
    raise web.seeother('/')

class RunBuild:
  def run(self, task_id):
    #i = web.input()
    i = {"task_id": task_id}
    selectedBuilds = db.select('builds', where="task_id=" + str(i["task_id"]))

    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if selectedBuilds:
      db.update('builds', where="task_id=" + str(i["task_id"]), last_build_date=date_now)

    taskBuilder = TaskBuilder('http://localhost:8080')

    for build in selectedBuilds:
      taskBuilder.add_build(repos=build.repos, branch=build.branch, version=build.version, author=build.author, styleguide_repo=build.styleguide_repo,
        styleguide_branch=build.styleguide_branch, sidecar_repo=build.sidecar_repo, sidecar_branch=build.sidecar_branch,
        package_list=build.package_list, upgrade_package=build.upgrade_package)
    #raise web.seeother('/')

class Build:
  def GET(self):

    i = web.input()
    selectedBuilds = db.select('builds', where="task_id=" + i.task_id, what="task_id")

    if selectedBuilds:
      builds_status = db.select('builds_status')

      if builds_status:
        max_priority_records = db.query('select max(priority) as priority from builds_status')
        new_max_priority = max_priority_records[0].priority + 1

        db.insert('builds_status', task_id=int(i.task_id), priority=new_max_priority, status="InQueue")
        statusString = json.JSONEncoder().encode({"task_id": i.task_id, "status": "InQueue" })
      else:
        db.insert('builds_status',
              task_id=int(i.task_id),
              status="Running",
              priority=1)
        RunBuild().run(i.task_id)
        statusString = json.JSONEncoder().encode({"task_id": i.task_id, "status": "Running" })

      return statusString

class UpdateBuild:
  def POST(self):
    i = web.input(all_language_packs="0")

    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #Before update
    f = open("logger", "a")
    for m in db.select('builds', where="task_id =" +  i.task_id):
      f.write(date_now + " [Before Update Action:]" + str(m.task_id) + "," + m.repos + "," + m.branch + "," + m.version + "," + m.author + "," + m.styleguide_repo + "," + m.styleguide_branch + "," + m.sidecar_repo + "," + m.sidecar_branch + "," + m.package_list + "," + "\n")

    selectedBuilds = db.select('builds', where="task_id=" + i.task_id)

    buildUtil = BuildUtil()
    i = buildUtil.sanitize_input(i)
    styleguide_branch = buildUtil.determine_styleguide_branch(i.styleguide_repo, i.styleguide_branch, i.version)

    if selectedBuilds:
      db.update('builds', where="task_id=" + i.task_id, repos=i.repos, branch=i.branch, version=i.version, author=i.author,
        styleguide_repo=i.styleguide_repo, styleguide_branch=styleguide_branch, sidecar_repo=i.sidecar_repo,
        sidecar_branch=i.sidecar_branch, package_list=i.package_list, upgrade_package=i.upgrade_package)

      #After update
      for k in db.select('builds', where="task_id =" +  i.task_id):
        f.write(date_now + " [After Update Action:]" + str(k.task_id) + "," + k.repos + "," + k.branch + "," + k.version + "," + k.author + "," + k.styleguide_repo + "," + k.styleguide_branch + "," + k.sidecar_repo + "," + k.sidecar_branch + "," + k.package_list + "\n")

    f.close()
    #End logger

    raise web.seeother('/')

class GetBuild:
  def GET(self):
    i = web.input()
    buildString = ""
    selectedBuilds = db.select('builds', where="task_id=" + i.task_id)

    if selectedBuilds:
      for x in  selectedBuilds:
        buildString = json.JSONEncoder().encode({"repos": x.repos, "branch": x.branch, "version": x.version, "author": x.author,
          "styleguide_repo": x.styleguide_repo, "styleguide_branch": x.styleguide_branch, "sidecar_repo": x.sidecar_repo,
          "sidecar_branch": x.sidecar_branch, "package_list": x.package_list, "upgrade_package": x.upgrade_package})
      web.header('Content-type', 'application/json')
      return buildString

class BuildCron:
  def __init__(self):
    self.taskBuilder = TaskBuilder(appconfig.jenkins_url)

  def check_queue(self):
    #Check queue jobs
    j = self.taskBuilder.j

    return j.get_queue_info()

  def is_building_job(self, jobName):
    if str(jobName) in self.get_building_job():
      return True
    else:
      return False

  def get_building_job(self):
    #Check building job

    j = self.taskBuilder.j
    job_list = j.get_jobs()
    job_queue_list = j.get_queue_info()
    running_job = []

    for job in job_list:
      if re.search('anime', job['color']) and re.match('^Build_', job['name']):
        running_job.append(job['name'])

    for queue_item in job_queue_list:
      if re.match('^Build_', queue_item['task']['name']):
          running_job.append(queue_item['task']['name'])

    return running_job

  def get_lowest_build(self):
    min_builds = db.query('select task_id, status, priority \
           from builds_status \
           where priority=(select min(b.priority) from builds_status as b)')
    if min_builds:
      for min_build in min_builds:
        return {"task_id":min_build.task_id, "status": min_build.status, "priority": min_build.priority}

    #min_build_priority = min_build_priorities[0].priority

    #if min_build_priority:
    #  selectedBuildTasks = db.select('builds_status', where='priority=' + str(min_build_priority))
    #  for selectBuildTask in selectedBuildTasks:
    #    return {"task_id":selectBuildTask.task_id, "status": selectBuildTask.status}
    #else:
    #  return False

  def update_task_status_as_lastBuild(self, task_id, jobName):
    j = self.taskBuilder
    job_status = j.get_build_status(jobName)

    if job_status == False or job_status == 'Succcess':
      job_status = 'Available'

    db.update('builds', where="task_id=" + str(task_id), status=job_status)

  def run_cron(self):
    lowest_build = self.get_lowest_build()
    job_list = []

    if lowest_build:
      if lowest_build["status"] == 'Running':
        selectRepos = db.select('builds', where='task_id=' + str(lowest_build['task_id']), what="repos")
        buildUtil = BuildUtil()
        jobName = ""
        for m in selectRepos:
          jobName = buildUtil.get_job_name(repos=m["repos"])

        if self.is_building_job(jobName):
          pass
        else:
          #update build_status and remove the running flag
          self.update_task_status_as_lastBuild(str(lowest_build['task_id']), jobName)
          db.delete('builds_status', where='task_id=' + str(lowest_build["task_id"]))

      elif lowest_build["status"] == 'InQueue':
        #Assume Jenkins is avaliable for building
        RunBuild().run(lowest_build["task_id"])
        db.update('builds_status', where='task_id=' + str(lowest_build["task_id"]), status='Running')

      else:
        #print 'false with invalid status'
        pass
    else:
      #print 'false from lowest build'
      pass
    
    for x in db.select('builds_status', what='task_id, status'):
      job_list.append(x)

    return job_list
      
  
  def GET(self):
    job_list = []
    new_builds_status = self.run_cron()
    web.header('Content-type', 'application/json')
    if new_builds_status:
      for build_status in new_builds_status:
        job_list.append({"task_id": build_status.task_id, "status": build_status.status})

    return json.JSONEncoder().encode(job_list)

class FullView:
  def POST(self):
    i = web.input()
    builds = db.select('builds', where="task_id =" +  i.task_id)

    return render.view(builds)


  def GET(self):
    i = web.input()
    builds = db.select('builds', where="task_id =" +  i.task_id)

    return render.view(builds)

class Fixing:
  def GET(self):
    i = web.input()

    return render.fixing(appconfig.site_url)

class SendMailToAdmin:
  def POST(self):
    i = web.input()
    web.sendmail(i.from_address, 'oyang@sugarcrm.com', 'BranchBuilder - ' + i.subject, i.message)

class Logger:
  def GET(self):
    web.header('Content-type', 'text/plain')
    f = open("logger", "r")
    return f.read()
    
if __name__ == '__main__':
  app.run()
