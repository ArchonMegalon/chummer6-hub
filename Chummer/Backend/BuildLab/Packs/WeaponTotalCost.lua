local total = Context.OwnCost

for i = 0, Context.WeaponAccessories.Count - 1 do
    total = total + Context.WeaponAccessories[i].TotalCost
end

for i = 0, Context.Children.Count - 1 do
    total = total + Context.Children[i].TotalCost
end

return total
