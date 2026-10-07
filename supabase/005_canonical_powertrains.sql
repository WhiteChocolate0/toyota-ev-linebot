-- Standardise all future vehicle records.  Legacy values remain readable by the app,
-- but new rows must use these five codes.
alter table vehicle_profiles drop constraint if exists vehicle_profiles_drivetrain_check;
update vehicle_profiles
set drivetrain = case drivetrain
  when 'gasoline' then 'ICE_GASOLINE'
  when 'diesel' then 'ICE_DIESEL'
  when 'hybrid' then 'HEV'
  when 'phev' then 'PHEV'
  when 'ev' then 'BEV'
  else drivetrain
end;
alter table vehicle_profiles
  add constraint vehicle_profiles_drivetrain_check
  check (drivetrain in ('ICE_GASOLINE', 'ICE_DIESEL', 'HEV', 'PHEV', 'BEV'));
